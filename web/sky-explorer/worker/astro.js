// FITS image reader and TAN-SIP astrometry for the SPHEREx cutouts.
export function readFits(buffer) {
  const bytes = new Uint8Array(buffer), view = new DataView(buffer), hdus = [];
  const decoder = new TextDecoder('ascii');
  let offset = 0;
  while (offset + 2880 <= buffer.byteLength) {
    const header = {}; let cursor = offset, ended = false;
    for (; cursor + 80 <= buffer.byteLength; cursor += 80) {
      const card = decoder.decode(bytes.subarray(cursor, cursor + 80));
      const key = card.slice(0, 8).trim();
      if (key === 'END') {cursor += 80; ended = true; break;}
      if (card[8] !== '=') continue;
      const raw = card.slice(10).trim();
      let value;
      if (raw.startsWith("'")) value = raw.slice(1, raw.indexOf("'", 1)).trim();
      else {
        const v = raw.split('/')[0].trim();
        value = v === 'T' ? true : v === 'F' ? false : Number(v.replace(/D/g, 'E'));
      }
      header[key] = value;
    }
    if (!ended) throw new Error('Cabeçalho FITS incompleto.');
    const start = offset + Math.ceil((cursor - offset) / 2880) * 2880;
    const count = header.NAXIS ? Array.from({length: header.NAXIS}, (_, i) => header[`NAXIS${i+1}`]).reduce((a,b)=>a*b,1) : 0;
    const size = count * Math.abs(header.BITPIX || 8) / 8 + (header.PCOUNT || 0);
    if (start + size > buffer.byteLength) throw new Error('Arquivo FITS truncado.');
    const hdu = {header, start, size, view};
    if (header.XTENSION !== 'BINTABLE' && count) {
      const data = new Float64Array(count), step = Math.abs(header.BITPIX)/8;
      const read = {'-32':'getFloat32','-64':'getFloat64','16':'getInt16','32':'getInt32','8':'getUint8'}[header.BITPIX];
      if (!read) throw new Error(`BITPIX ${header.BITPIX} não suportado.`);
      for(let i=0;i<count;i++) data[i]=view[read](start+i*step,false)*(header.BSCALE??1)+(header.BZERO??0);
      hdu.data=data;
    }
    hdus.push(hdu);
    offset = start + Math.ceil(size/2880)*2880;
  }
  return hdus;
}
export function tableColumn(hdu, name) {
  const h = hdu.header; let off = hdu.start;
  const sizes={E:4,D:8,J:4,I:2,K:8,A:1,B:1,L:1};
  for(let i=1;i<=h.TFIELDS;i++) {
    const m=String(h[`TFORM${i}`]).match(/^(\d*)([A-Z])/);
    if(!m || !sizes[m[2]]) throw new Error('Formato FITS de tabela não suportado.');
    const n=Number(m[1]||1), code=m[2], step=sizes[code];
    if(h[`TTYPE${i}`]===name) {
      const method={E:'getFloat32',D:'getFloat64',J:'getInt32',I:'getInt16',B:'getUint8'}[code];
      if(!method) throw new Error('Coluna FITS não numérica.');
      return Array.from({length:n},(_,j)=>hdu.view[method](off+j*step,false));
    }
    off+=n*step;
  }
  return null;
}
const rad=Math.PI/180;
function poly(h,p,u,v) {let s=0;for(let i=0;i<=(h[`${p}_ORDER`]||0);i++) for(let j=0;j<=(h[`${p}_ORDER`]||0)-i;j++) s+=(h[`${p}_${i}_${j}`]||0)*u**i*v**j;return s;}
export function worldPixel(h,ra,dec) {
  const a=ra*rad,d=dec*rad,a0=h.CRVAL1*rad,d0=h.CRVAL2*rad;
  const c=Math.sin(d)*Math.sin(d0)+Math.cos(d)*Math.cos(d0)*Math.cos(a-a0);
  if(c<=0) return [NaN,NaN];
  const xi=Math.cos(d)*Math.sin(a-a0)/c/rad;
  const eta=(Math.sin(d)*Math.cos(d0)-Math.cos(d)*Math.sin(d0)*Math.cos(a-a0))/c/rad;
  const cd11=h.CD1_1??(h.CDELT1??1)*(h.PC1_1??1), cd12=h.CD1_2??(h.CDELT1??1)*(h.PC1_2??0);
  const cd21=h.CD2_1??(h.CDELT2??1)*(h.PC2_1??0), cd22=h.CD2_2??(h.CDELT2??1)*(h.PC2_2??1);
  const det=cd11*cd22-cd12*cd21;
  const U=(cd22*xi-cd12*eta)/det,V=(-cd21*xi+cd11*eta)/det;
  let u=U,v=V;
  // Solve the inverse SIP distortion numerically; CRPIX refers to the cutout WCS.
  for(let k=0;k<15;k++) {
    const f=u+poly(h,'A',u,v)-U,g=v+poly(h,'B',u,v)-V;
    if(Math.max(Math.abs(f),Math.abs(g))<1e-6)break;
    const e=.01;
    const fu=1+(poly(h,'A',u+e,v)-poly(h,'A',u-e,v))/(2*e);
    const fv=(poly(h,'A',u,v+e)-poly(h,'A',u,v-e))/(2*e);
    const gu=(poly(h,'B',u+e,v)-poly(h,'B',u-e,v))/(2*e);
    const gv=1+(poly(h,'B',u,v+e)-poly(h,'B',u,v-e))/(2*e);
    const den=fu*gv-fv*gu;
    u-=(gv*f-fv*g)/den;v-=(-gu*f+fu*g)/den;
  }
  return [u+h.CRPIX1-1,v+h.CRPIX2-1];
}
export function skyAt(ra,dec,x,y,size,fov) {
  const xi=-(x-(size-1)/2)*fov/size/3600*rad,eta=(y-(size-1)/2)*fov/size/3600*rad;
  const d=dec*rad,a=ra*rad,den=Math.cos(d)-eta*Math.sin(d);
  return [(a+Math.atan2(xi,den))/rad,Math.atan2(Math.sin(d)+eta*Math.cos(d),Math.sqrt(den*den+xi*xi))/rad];
}
function bilerp(data,w,h,x,y,valid=null) {
  const x0=Math.floor(x),y0=Math.floor(y);let sum=0,weight=0;
  for(let dy=0;dy<=1;dy++)for(let dx=0;dx<=1;dx++) {
    const xx=x0+dx,yy=y0+dy;
    if(xx<0||yy<0||xx>=w||yy>=h)continue;
    const i=yy*w+xx,v=data[i],q=(dx?x-x0:1-(x-x0))*(dy?y-y0:1-(y-y0));
    if(Number.isFinite(v)&&(!valid||valid(i))){sum+=v*q;weight+=q;}
  }
  return weight>.5?sum/weight:NaN;
}
function linear(xs,v) {let j=0;while(j<xs.length-2&&xs[j+1]<v)j++;return [j,(v-xs[j])/(xs[j+1]-xs[j])];}
export function wavelengthMap(hdus) {
  const image=hdus.find(x=>x.header.EXTNAME==='IMAGE'),table=hdus.find(x=>x.header.EXTNAME==='WCS-WAVE');
  if(!image||!table)return ()=>NaN;
  const xs=tableColumn(table,'X'),ys=tableColumn(table,'Y'),values=tableColumn(table,'VALUES');
  return (x,y)=> {
    const [ix,fx]=linear(xs,x+2-image.header.CRPIX1A),[iy,fy]=linear(ys,y+2-image.header.CRPIX2A);
    const at=(xx,yy)=>values[(yy*xs.length+xx)*2];
    return (1-fy)*((1-fx)*at(ix,iy)+fx*at(ix+1,iy))+fy*((1-fx)*at(ix,iy+1)+fx*at(ix+1,iy+1));
  };
}
// Mirrors the instrumental bad-pixel bits used by the Python pipeline.
export const BAD_BITS = 0xFFDFFFFF; // SOURCE (bit 21) alone is not a bad pixel
export function projectExposure(hdus,config) {
  const im=hdus.find(x=>x.header.EXTNAME==='IMAGE');if(!im)throw new Error('FITS sem IMAGE.');
  const vari=hdus.find(x=>x.header.EXTNAME==='VARIANCE'),flags=hdus.find(x=>x.header.EXTNAME==='FLAGS'),zodi=hdus.find(x=>x.header.EXTNAME==='ZODI');
  const h=im.header,w=h.NAXIS1,ht=h.NAXIS2,size=config.size;
  const wave=wavelengthMap(hdus),data=new Float64Array(im.data.length),valid=new Uint8Array(data.length);
  let masked=0;
  for(let i=0;i<data.length;i++) {
    data[i]=im.data[i]-(zodi?.data[i]||0);
    const wl=wave(i%w,Math.floor(i/w));
    valid[i]=Number.isFinite(data[i])&&(!flags||!((flags.data[i]>>>0)&(config.badMask>>>0)))&&(!vari||Number.isFinite(vari.data[i])&&vari.data[i]>0)&&(!config.band||wl>=config.band.min&&wl<config.band.max);
    if(!valid[i])masked++;
  }
  const output=new Float64Array(size*size),variance=new Float64Array(size*size);output.fill(NaN);variance.fill(Infinity);
  for(let y=0;y<size;y++)for(let x=0;x<size;x++) {
    const [ra,dec]=skyAt(config.ra,config.dec,x,y,size,config.fov),[sx,sy]=worldPixel(h,ra,dec),i=y*size+x;
    if(!Number.isFinite(sx)||!Number.isFinite(sy))continue;
    output[i]=bilerp(data,w,ht,sx,sy,j=>valid[j]);
    variance[i]=vari?bilerp(vari.data,w,ht,sx,sy,j=>valid[j]):1;
  }
  return {data:output,variance,date:h['DATE-AVG']||h['DATE-OBS'],mjd:h['MJD-AVG']||h['MJD-OBS'],wave:wave(...worldPixel(h,config.ra,config.dec)),masked:masked/data.length,detector:h.DETECTOR};
}
export function coadd(exposures,size) {
  const data=Array(size*size).fill(null),hits=Array(size*size).fill(0),weights=Array(size*size).fill(0),sum=Array(size*size).fill(0);
  for(const e of exposures)for(let i=0;i<data.length;i++)if(Number.isFinite(e.data[i])&&Number.isFinite(e.variance[i])&&e.variance[i]>0){const w=1/e.variance[i];sum[i]+=e.data[i]*w;weights[i]+=w;hits[i]++;}
  for(let i=0;i<data.length;i++)if(weights[i])data[i]=sum[i]/weights[i];
  return {data,hits,weights};
}
export function groupEpochs(exposures,mode='visit') {
  const sorted=[...exposures].sort((a,b)=>a.mjd-b.mjd),groups=[];
  if(mode==='individual')return sorted.map(e=>[e]);
  for(const e of sorted) {
    const key=mode==='semester'?`${new Date((e.mjd-40587)*864e5).getUTCFullYear()}-${new Date((e.mjd-40587)*864e5).getUTCMonth()<6?'H1':'H2'}`:null;
    const last=groups.at(-1);
    if(!last||mode==='visit'&&e.mjd-last.at(-1).mjd>14||mode==='semester'&&last.key!==key){const g=[e];g.key=key;groups.push(g);}else last.push(e);
  }
  return groups;
}
export function quantile(values,q) {const a=values.filter(x=>x!==null&&Number.isFinite(x)).sort((a,b)=>a-b);return a.length?a[Math.floor((a.length-1)*q)]:0;}
export function parseCoordinate(text,isRA) {
  const v=text.trim();if(!v)throw new Error('Informe RA e declinação.');
  if(/^[-+]?\d+(\.\d+)?$/.test(v)){const n=Number(v);if(isRA&&(n<0||n>=360)||!isRA&&(n< -90||n>90))throw new Error('RA: 0–360 graus; declinação: −90–90 graus.');return n;}
  const nums=v.match(/[-+]?\d+(?:\.\d+)?/g)?.map(Number);if(!nums||nums.length!==3||Math.abs(nums[1])>=60||Math.abs(nums[2])>=60)throw new Error('Use graus decimais ou hh:mm:ss / ±dd:mm:ss.');
  const sign=v.startsWith('-')?-1:1,n=sign*(Math.abs(nums[0])+Math.abs(nums[1])/60+Math.abs(nums[2])/3600)*(isRA?15:1);
  if(isRA&&(n<0||n>=360)||!isRA&&(n< -90||n>90))throw new Error('Coordenadas fora do intervalo.');return n;
}
export function imageFits(data,{ra,dec,size,fov}) {
  const cards=[];
  const put=(k,v)=>{const repr=typeof v==='string'?`'${v}'`:v===true?'T':String(v);cards.push((k.padEnd(8)+'= '+repr.padStart(20)).padEnd(80));};
  put('SIMPLE',true);put('BITPIX',-32);put('NAXIS',2);put('NAXIS1',size);put('NAXIS2',size);
  put('CTYPE1','RA---TAN');put('CTYPE2','DEC--TAN');put('CUNIT1','deg');put('CUNIT2','deg');
  put('CRPIX1',(size+1)/2);put('CRPIX2',(size+1)/2);put('CRVAL1',ra);put('CRVAL2',dec);
  put('CDELT1',-fov/size/3600);put('CDELT2',fov/size/3600);put('BUNIT','MJy/sr');cards.push('END'.padEnd(80));
  const header=cards.join('').padEnd(Math.ceil(cards.length*80/2880)*2880);
  const result=new Uint8Array(header.length+Math.ceil(size*size*4/2880)*2880);
  result.set(new TextEncoder().encode(header));const view=new DataView(result.buffer);
  for(let i=0;i<data.length;i++)view.setFloat32(header.length+i*4,data[i]===null?NaN:data[i],false);
  return result;
}
