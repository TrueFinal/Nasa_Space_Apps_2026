import { installHelp } from './help.js';
import {ArchiveBrowser} from './catalogue.js';
import {readFits,projectExposure,coadd,groupEpochs,quantile,parseCoordinate,imageFits,intervalStack} from './astro.js';
import {GIFEncoder,quantize,applyPalette} from './gifenc.js';
const $=id=>document.getElementById(id), cfg=await fetch(new URL('./config.json',import.meta.url)).then(r=>r.json());
const integrated = new URL(import.meta.url).pathname.startsWith('/sky-assets/');
let raw=[],groups=[],frames=[],dataset=null,current=0,mode='image',timer=null,controller=null,job=0,aladin=null,spectrumRows=[],point=null,gaiaCatalog=null,gaiaKey='',mapBlob=null;
let catalogueContext=null,displayLimits=new Map(),playbackWanted=false,stackCache=null,exportingGif=false;
const archive=new ArchiveBrowser($('catalogue'),openArchiveImage);
installHelp();
const canvas=$('sky'),ctx=canvas.getContext('2d'),mini=document.createElement('canvas'),mc=mini.getContext('2d');
const status=(s,error=false)=>{$('status').textContent=s;$('status').classList.toggle('error',error);};
const utc=mjd=>new Date((mjd-40587)*864e5).toISOString().slice(0,19)+' UTC';
const iso=mjd=>new Date((mjd-40587)*864e5).toISOString().slice(0,10);
function stop(){playbackWanted=false;if(timer)clearInterval(timer);timer=null;$('play').textContent='▶';$('play').setAttribute('aria-label','Play animation');}
function download(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function bandOptions(){const old=$('band').value,det=Number($('detector').value);$('band').replaceChildren(new Option('Combine the detector range','detector'));cfg.channels.forEach((c,i)=>{if(c.DETECTOR===det)$('band').add(new Option(`Channel ${i+1} · ${c.WAVELENGTH.toFixed(3)} µm`,String(i+1)));});if([...$('band').options].some(o=>o.value===old))$('band').value=old;}
function configuration(){return {ra:parseCoordinate($('ra').value,true),dec:parseCoordinate($('dec').value,false),fov:Number($('fov').value),detector:Number($('detector').value),size:Math.max(8,Math.round(Number($('fov').value)/6.2))};}
function coordinateURL(){const c=configuration(),u=new URL(location.href);for(const k of ['ra','dec','fov','detector'])u.searchParams.set(k,c[k]);u.searchParams.set('band',$('band').value);u.searchParams.set('collection',$('collection').value);if(dataset?.isExample)u.searchParams.set('example',dataset.target.id);else u.searchParams.delete('example');for(const k of ['start','end'])if($(k).value)u.searchParams.set(k,$(k).value);else u.searchParams.delete(k);return u;}
function provenance(){return {app:'SPHEREx Sky Explorer',exported_at:new Date().toISOString(),dataset,mode,reference:Number($('reference').value),frames:frames.map(f=>({date:iso(f.mjd),n_images:f.exposures.length,obs_ids:f.exposures.map(e=>e.obs_id),coverage:f.data.filter(Number.isFinite).length/f.data.length})),exposures:raw.map(({data,variance,...r})=>r),palette:$('palette').value,display:'Shared 1–99.5% limits, optional asinh stretch. Browser TAN-SIP + bilinear resampling; not exact area-overlap.'};}
function dataForFrame(i){
  if(!frames.length)return [];
  if(mode==='mean'||mode==='trail'){if(!stackCache)stackCache=intervalStack(frames,dataset.size,Number($('stack-first').value)-1,Number($('stack-count').value),mode==='trail'?'max':'mean');return stackCache.data;}
  if(mode==='difference'){const ref=frames[Number($('reference').value)||0];return frames[i].data.map((v,j)=>Number.isFinite(v)&&Number.isFinite(ref.data[j])?v-ref.data[j]:null);}
  return frames[i].data;
}
function draw(){
  if(!frames.length)return;
  const stacked=mode==='mean'||mode==='trail',selected=stacked?frames.slice(Number($('stack-first').value)-1,Number($('stack-first').value)-1+Number($('stack-count').value)):null;
  const f=stacked?{...selected[0],exposures:selected.flatMap(f=>f.exposures)}:frames[current],data=dataForFrame(current),size=dataset.size;
  mini.width=mini.height=size;
  const pixels=mc.createImageData(size,size);
  const cacheKey=mode+':'+$('reference').value+':'+$('stack-first').value+':'+$('stack-count').value;
  if(!displayLimits.has(cacheKey)){
    const sample=[],step=Math.max(1,Math.ceil(frames.length*size*size/100000));
    for(let fi=0;fi<frames.length;fi++){const values=mode==='difference'?dataForFrame(fi):frames[fi].data;for(let j=0;j<values.length;j+=step)sample.push(values[j]);}
    let lo=quantile(sample,.01),hi=quantile(sample,.995);
    if(mode==='difference'){hi=Math.max(Math.abs(quantile(sample,.01)),Math.abs(quantile(sample,.99)),1e-8);lo=-hi;}
    if(hi<=lo)hi=lo+1;displayLimits.set(cacheKey,[lo,hi]);
  }
  const [lo,hi]=displayLimits.get(cacheKey);
  const legend=document.querySelector('.intensity-scale');legend.hidden=$('palette').value!=='gray'||mode==='difference';
  if(!legend.hidden){const inverted=$('invert').checked;legend.children[0].textContent='Fainter · '+(inverted?'white':'black');legend.children[1].style.background=inverted?'linear-gradient(to right,white,black)':'linear-gradient(to right,black,white)';legend.children[2].textContent='Brighter · '+(inverted?'black':'white');}
  let count=0;
  for(let y=0;y<size;y++)for(let x=0;x<size;x++) {
    const v=data[y*size+x],j=((size-1-y)*size+x)*4;
    let rgb=(x+y)%4<2?[195,195,195]:[225,225,225];
    if(v!==null&&Number.isFinite(v)){
      count++;
      if(mode==='difference'){const t=Math.max(-1,Math.min(1,v/hi));const gray=127.5*(1-t);rgb=[gray,gray,gray];}
      else{let t=Math.max(0,Math.min(1,(v-lo)/(hi-lo)));if($('stretch').value==='asinh')t=Math.asinh(8*t)/Math.asinh(8);if($('invert').checked)t=1-t;rgb=$('palette').value==='inferno'?cfg.inferno[Math.round(t*255)]:[t*255,t*255,t*255];}
    }
    for(let c=0;c<3;c++)pixels.data[j+c]=rgb[c];pixels.data[j+3]=255;
  }
  mc.putImageData(pixels,0,0);ctx.imageSmoothingEnabled=false;ctx.drawImage(mini,0,0,canvas.width,canvas.height);
  if(point){ctx.strokeStyle='#a6ebd0';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc((point.x+.5)*canvas.width/size,(size-point.y-.5)*canvas.height/size,2*canvas.width/size,0,2*Math.PI);ctx.stroke();}
  ctx.fillStyle='#080d12cc';ctx.fillRect(0,0,canvas.width,27);ctx.fillStyle='#e6eeee';ctx.font='12px monospace';ctx.fillText(`SPHEREx ${dataset.bandLabel} | ${iso(f.mjd)} | ${current+1}/${frames.length}`,10,18);
  $('empty').hidden=count>0;$('frame').value=current;$('frame-label').textContent=`${current+1} / ${frames.length}`;
  $('play').disabled=frames.length<2||mode==='map'||mode==='mean'||mode==='trail';$('gif').disabled=exportingGif||frames.length<2||!['image','difference'].includes(mode);
  $('playback-note').textContent=frames.length<2?'Only one frame has coverage. Expand the dates or select a saved sequence.':frames.length+' time frames · '+(dataset.isExample?'saved real observations':'archive query');
  $('image-caption').textContent=`${iso(f.mjd)} · ${f.exposures.length} exposures · coverage ${Math.round(count/data.length*100)}%`;
  [...$('epochs').children].forEach((e,i)=>e.classList.toggle('active',i===current));
  const waves=f.exposures.map(e=>e.wave).filter(Number.isFinite),mask=f.exposures.reduce((s,e)=>s+(e.masked||0),0)/f.exposures.length;
  const info=[['Start UTC',utc(f.exposures[0].mjd)],['End UTC',utc(f.exposures.at(-1).mjd)],['Exposures',String(f.exposures.length)],['Exposure wavelength centres',waves.length?`${Math.min(...waves).toFixed(3)}–${Math.max(...waves).toFixed(3)} µm`:'—'],['Rejected pixels',`${Math.round(mask*100)}% (mean)`],['Unit','MJy/sr'],['Collection',dataset.collection],['Frame coverage',`${Math.round(count/data.length*100)}%`]];
  $('metadata').replaceChildren();for(const [a,b] of info){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=a;dd.textContent=b;$('metadata').append(dt,dd);}
  $('exposure-links').replaceChildren();for(const e of f.exposures){if(!e.url)continue;const a=document.createElement('a');a.href=e.url;a.textContent=`${e.obs_id} ↗`;a.target='_blank';a.rel='noopener';$('exposure-links').append(a);}
}
function rebuild(){
  stop();displayLimits.clear();stackCache=null;if(!dataset)return;mode='image';document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode==='image'));$('sky').hidden=false;$('aladin').hidden=true;
  groups=groupEpochs(raw,$('group').value);frames=groups.map(exposures=>({...coadd(exposures,dataset.size),exposures,mjd:exposures.reduce((s,e)=>s+e.mjd,0)/exposures.length}));
  current=0;$('stack-first').value=1;$('stack-first').max=frames.length;$('stack-count').max=frames.length;$('stack-count').value=Math.min(3,frames.length);updateStackRange();$('frame').max=Math.max(0,frames.length-1);$('reference').replaceChildren();$('epochs').replaceChildren();
  frames.forEach((f,i)=>{const date=$('group').value==='individual'?new Date((f.mjd-40587)*864e5).toISOString().slice(0,19):iso(f.mjd);$('reference').add(new Option(date,i));const b=document.createElement('button');b.className='epoch';b.textContent=date;const small=document.createElement('small');small.textContent=`${f.exposures.length} exposures`;b.append(small);b.onclick=()=>{stop();current=i;draw();if(mode==='map')openMap();};$('epochs').append(b);});
  $('source-badge').textContent=dataset.isExample?'SAVED REAL OBSERVATIONS':'LIVE ARCHIVE QUERY';
  $('target-title').textContent=dataset.title||`${dataset.ra.toFixed(5)}°, ${dataset.dec.toFixed(5)}°`;
  $('irsa').href=`https://irsa.ipac.caltech.edu/applications/spherex/?UserTargetWorldPt=${dataset.ra}%20${dataset.dec}%20eq%20j2000`;
  draw();drawSpectrum();if(mode==='map')openMap();else startPlayback();
}
function drawSpectrum(){
  const c=$('spectrum'),cctx=c.getContext('2d');cctx.clearRect(0,0,c.width,c.height);cctx.fillStyle='#93a7b1';cctx.font='13px sans-serif';
  if(!dataset||!raw.length)return;
  const p=point||{x:(dataset.size-1)/2,y:(dataset.size-1)/2};
  const factor=1e9*(dataset.fov/dataset.size/3600*Math.PI/180)**2;
  spectrumRows=[];$('spectrum-note').textContent='No aperture measurements at this position in the loaded wavelength range.';
  for(const e of raw){let sum=0,n=0,background=[];for(let y=0;y<dataset.size;y++)for(let x=0;x<dataset.size;x++){const d=Math.hypot(x-p.x,y-p.y),v=e.data[y*dataset.size+x];if(v===null||!Number.isFinite(v))continue;if(d<=2){sum+=v;n++;}else if(d>=4&&d<=6)background.push(v);}if(n&&background.length&&Number.isFinite(e.wave))spectrumRows.push({wavelength_um:e.wave,flux_mjy:(sum-quantile(background,.5)*n)*factor,date:iso(e.mjd),obs_id:e.obs_id});}
  spectrumRows.sort((a,b)=>a.wavelength_um-b.wavelength_um);
  if(!spectrumRows.length){cctx.fillText('No spectral coverage at the selected position.',40,100);return;}
  const points=spectrumRows,lo=Math.min(...points.map(p=>p.flux_mjy)),hi=Math.max(...points.map(p=>p.flux_mjy));
  const d=cfg.channels.filter(c=>c.DETECTOR===dataset.detector),xmin=d[0]?.WL_MIN||.75,xmax=d.at(-1)?.WL_MAX||5.01;
  cctx.strokeStyle='#344752';cctx.beginPath();cctx.moveTo(55,12);cctx.lineTo(55,180);cctx.lineTo(680,180);cctx.stroke();
  cctx.fillText(`${hi.toPrecision(3)} mJy`,2,25);cctx.fillText(`${lo.toPrecision(3)}`,2,180);cctx.fillText(`${xmin.toFixed(2)} µm`,55,210);cctx.fillText(`${xmax.toFixed(2)} µm`,610,210);
  for(const pt of points){const x=55+(pt.wavelength_um-xmin)/(xmax-xmin)*625,y=170-(pt.flux_mjy-lo)/(hi-lo||1)*145;cctx.fillStyle='#a6ebd0';cctx.beginPath();cctx.arc(x,y,4,0,2*Math.PI);cctx.fill();}
  $('spectrum-note').textContent=`${points.length} aperture measurements. Radius: 2 pixels; background annulus: 4–6 pixels. Mixed epochs; exploratory use. Pixel ${Math.round(p.x)}, ${Math.round(p.y)}.`;
}
function parseCSV(text){let rows=[],row=[],cell='',quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(!quoted&&(c===','||c==='\n')){row.push(cell.replace(/\r$/,''));cell='';if(c==='\n'){rows.push(row);row=[];}}else cell+=c;}if(cell||row.length){row.push(cell);rows.push(row);}const keys=rows.shift()||[];return rows.filter(r=>r.length>=keys.length).map(r=>Object.fromEntries(keys.map((k,i)=>[k,r[i]])));}
async function get(url,signal){if(integrated){if(url.startsWith('/api/'))url=url.replace('/api/','/sky-api/');else if(url.startsWith('/samples/'))url='/sky-assets'+url;}const r=await fetch(url,{signal});if(!r.ok){let m;try{m=(await r.json()).error;}catch{}throw new Error(m||`HTTP ${r.status}`);}return r;}
async function loadExample(t){
  controller?.abort();const id=++job;stop();$('cancel').hidden=true;$('search-button').disabled=false;$('progress').hidden=true;status(`Opening real observations of ${t.name}…`);
  try{const d=await (await get(`/samples/${t.id}.json`)).json();if(id!==job)return;if(!d.exposures?.length)throw new Error('Saved example unavailable; search the archive.');
    $('start').value='';$('end').value='';$('ra').value=t.ra;$('dec').value=t.dec;$('detector').value=t.detector;$('fov').value=d.fov;$('fov-label').value=`${d.fov}″`;$('band').value='detector';bandOptions();
    catalogueContext={ra:d.ra,dec:d.dec,fov:d.fov,size:d.size,detector:t.detector};
    archive.setRows(d.exposures.map(e=>({obs_id:e.obs_id,date:e.date,t_min:e.mjd,energy_bandpassname:`SPHEREx-D${t.detector}`,collection:d.collection,access_url:e.url})),`Saved example: only ${d.exposures.length} sampled files. Use “List all images” to refresh the full archive catalogue.`);
    raw=d.exposures;dataset={...d,isExample:true,detector:t.detector,title:t.name,bandLabel:`D${t.detector}`,exposures:undefined};point=null;rebuild();
    status(`Real observations: ${raw.length} of ${d.archive_count} exposures D${t.detector} from DR1, in ${frames.length} time frames. Saved subset; search current data for more.${d.errors?.length?` ${d.errors.length} downloads failed while preparing the example.`:''}`);
    [...$('targets').children].forEach(b=>b.classList.toggle('active',b.dataset.id===t.id));history.replaceState({},'',coordinateURL());
  }catch(e){status(e.message,true);}
}
async function query(event){
  event?.preventDefault();let c;try{c=configuration();}catch(e){status(e.message,true);return;}
  controller?.abort();controller=new AbortController();const signal=controller.signal,id=++job;stop();$('cancel').hidden=false;$('search-button').disabled=true;$('progress').hidden=false;$('progress').value=0;
  const failures=[];
  try{
    status('Querying IRSA exposures…');
    if($('start').value&&$('end').value&&$('end').value<$('start').value)throw new Error('End date must follow the start date.');
    const collection=$('collection').value,collections=collection==='all'?['spherex_dr1','spherex_qr3','spherex_dr1_deep','spherex_qr3_deep']:collection==='both'?['spherex_dr1','spherex_qr3']:[collection];let rows=[];
    const batches=await Promise.all(collections.map(async col=>{try{const r=await get(`/api/archive?ra=${c.ra}&dec=${c.dec}&fov=${c.fov}&collection=${col}&refresh=1&start=${encodeURIComponent($('start').value)}&end=${encodeURIComponent($('end').value)}`,signal);return parseCSV(await r.text()).map(r=>({...r,collection:col}));}catch(e){if(signal.aborted)throw e;failures.push(`${col}: ${e.message}`);return [];}}));rows=batches.flat();
    if(!rows.length)throw new Error(failures.join(' · ')||'No exposures available in this region.');
    catalogueContext={...c};
    archive.setRows(rows,`Query ${collections.join(' + ')}: returned files from all six detectors. Applied date filters: ${$('start').value||'all available'} to ${$('end').value||'latest available'}. ${failures.length?'One collection failed; this catalogue may be incomplete.':''}`);
    if($('limit').value==='catalogue'){status(`${archive.rows.length} files listed. Use “View” to open any image. The previous display remains until another image is opened.`);return;}
    // DR1 takes precedence where the same exposure/detector is present in QR3.
    const unique=new Map();for(const row of rows)if(row.energy_bandpassname===`SPHEREx-D${c.detector}`&&!unique.has(row.obs_id))unique.set(row.obs_id,row);
    rows=[...unique.values()].sort((a,b)=>Number(a.t_min)-Number(b.t_min));
    const total=rows.length;if(!total)throw new Error('No images for this detector in the selected region.');
    const max=Number($('limit').value);if($('limit').value!=='all'&&rows.length>max){const indices=Array.from({length:max},(_,i)=>Math.round(i*(rows.length-1)/(max-1)));rows=indices.map(i=>rows[i]);}
    const plane=$('band').value==='detector'?null:cfg.channels[Number($('band').value)-1];const band=plane?{min:plane.WL_MIN,max:plane.WL_MAX}:null;
    const exposures=[];let done=0,next=0;
    async function consume(){while(next<rows.length){const row=rows[next++];if(signal.aborted)throw new DOMException('Cancelled','AbortError');try{
      status(`Downloading and aligning ${done+1}/${rows.length} images · detector D${c.detector}…`);
      const url=`/api/cutout?url=${encodeURIComponent(row.access_url)}&center=${c.ra},${c.dec}&size=${c.fov/3600}`;
      const r=await get(url,signal),hdus=readFits(await r.arrayBuffer());if(id!==job)return;
      const e=projectExposure(hdus,{...c,band,badMask:cfg.badMask});e.obs_id=row.obs_id;e.url=row.access_url;e.collection=row.collection;exposures.push(e);
    }catch(e){if(signal.aborted)throw e;failures.push(`${row.obs_id}: ${e.message}`);}finally{done++;$('progress').value=done/rows.length;}}}
    await Promise.all(Array.from({length:3},consume));if(id!==job)return;
    if(!exposures.length)throw new Error('Unable to download images. '+failures.slice(0,2).join(' · '));
    raw=exposures;dataset={...c,title:`${c.ra.toFixed(5)}°, ${c.dec.toFixed(5)}°`,bandLabel:plane?`${plane.WAVELENGTH.toFixed(3)} µm · channel ${$('band').value}`:`D${c.detector}`,band,collection,archive_count:total,sampled:rows.length<total,failures};point=null;
    rebuild();history.replaceState({},'',coordinateURL());status(`${raw.length}/${total} available exposures loaded · ${frames.length} frames · catalogue: ${archive.rows.length} files across all six detectors.${rows.length<total?' Download limit applied; increase it to include more images.':''}${failures.length?` ${failures.length} queries/downloads failed; see provenance.`:''}`);
  }catch(e){if(id===job)status(signal.aborted?'Loading cancelled. Previous images retained.':e.message,true);}
  finally{if(id===job){$('cancel').hidden=true;$('search-button').disabled=false;$('progress').hidden=true;}}
}
async function openArchiveImage(row){
  if(!catalogueContext)return;
  controller?.abort();controller=new AbortController();const signal=controller.signal,id=++job;stop();
  $('cancel').hidden=false;$('search-button').disabled=true;
  const detector=Number(row.energy_bandpassname.split('D').at(-1)),c={...catalogueContext,detector};
  try{
    status(`Opening ${row.obs_id} · D${detector}…`);
    const url=`/api/cutout?url=${encodeURIComponent(row.access_url)}&center=${c.ra},${c.dec}&size=${c.fov/3600}`;
    const response=await get(url,signal),e=projectExposure(readFits(await response.arrayBuffer()),{...c,badMask:cfg.badMask,band:null});
    if(id!==job)return;
    e.obs_id=row.obs_id;e.url=row.access_url;e.collection=row.collection;raw=[e];
    dataset={...c,collection:row.collection,title:row.obs_id,bandLabel:`D${detector}`,archive_count:archive.rows.length};point=null;
    mode='image';document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode==='image'));$('aladin').hidden=true;$('sky').hidden=false;$('play').disabled=false;
    rebuild();status(`Individual exposure ${row.obs_id} · ${row.collection}. Other files remain in the catalogue.`);
  }catch(e){if(id===job)status(signal.aborted?'Opening cancelled.':e.message,true);}
  finally{if(id===job){$('cancel').hidden=true;$('search-button').disabled=false;$('progress').hidden=true;}}
}
async function openMap(){
  if(!dataset)return;
  try{const {default:A}=await import('https://cdn.jsdelivr.net/npm/aladin-lite@3.9.2-beta/dist/aladin.js');await A.init;
    if(!aladin)aladin=A.aladin('#aladin',{survey:$('survey').value,fov:dataset.fov/3600,target:`${dataset.ra} ${dataset.dec}`});
    aladin.gotoRaDec(dataset.ra,dataset.dec);aladin.setFoV(dataset.fov/3600);aladin.setImageSurvey($('survey').value);
    if(mapBlob)URL.revokeObjectURL(mapBlob);
    mapBlob=URL.createObjectURL(new Blob([imageFits(frames[current].data,dataset)],{type:'application/fits'}));
    aladin.displayFITS(mapBlob,{opacity:.7},()=>{},()=>status('Unable to overlay the SPHEREx frame on the map.',true),'SPHEREx • current observation');
    const key=`${dataset.ra},${dataset.dec},${dataset.fov}`;
    if(gaiaKey!==key){gaiaCatalog?.hide();gaiaCatalog=null;gaiaKey=key;}
    if($('gaia').checked){
      gaiaCatalog?.hide();
      const response=await get(`/api/gaia?ra=${dataset.ra}&dec=${dataset.dec}&fov=${dataset.fov}`);
      const table=await response.json(),names=(table.metadata||table.columns).map(c=>c.name),year=2000+(frames[current].mjd-51544.5)/365.25;
      const sources=table.data.map(row=>{const r=Object.fromEntries(names.map((n,i)=>[n,row[i]]));const dt=year-(r.ref_epoch||2016);return A.source(r.ra+(r.pmra||0)*dt/3600000/Math.cos(r.dec*Math.PI/180),r.dec+(r.pmdec||0)*dt/3600000,{catalog:'Gaia DR3 / GAVO',G:r.phot_g_mean_mag,epoch:year.toFixed(2)});});
      gaiaCatalog=A.catalog({name:'Gaia DR3 • linear proper motion',color:'#a6ebd0',sourceSize:9,onClick:'showTable'});gaiaCatalog.addSources(sources);aladin.addCatalog(gaiaCatalog);
    }
    else gaiaCatalog?.hide();
  }catch(e){status(e.message,true);}
}
for(const t of cfg.targets){const b=document.createElement('button');b.type='button';b.className='target';b.dataset.id=t.id;b.textContent=t.name;const s=document.createElement('span');s.textContent=t.description;b.append(s);b.onclick=()=>loadExample(t);$('targets').append(b);}
$('search').onsubmit=query;$('load-all').onclick=()=>{$('limit').value='catalogue';$('collection').value='all';query();};$('cancel').onclick=()=>controller?.abort();$('fov').oninput=()=>{$('fov-label').value=`${$('fov').value}″`;};$('detector').onchange=bandOptions;
$('band').onchange=()=>{$('band-help').textContent=$('band').value==='detector'?'Broad range: spectral coverage varies. Search current data to apply.':'Fixed channel: pixels outside this range are masked in every epoch. Search current data to apply.';};
$('group').onchange=rebuild;$('frame').oninput=()=>{stop();current=Number($('frame').value);draw();if(mode==='map')openMap();};
function startPlayback(){
  if(frames.length<2||mode!=='image'&&mode!=='difference')return;
  stop();playbackWanted=true;if(document.hidden)return;
  $('play').textContent='Ⅱ';$('play').setAttribute('aria-label','Pause animation');
  timer=setInterval(()=>{current=(current+1)%frames.length;draw();},Number($('speed').value));
}
$('play').onclick=()=>timer?stop():startPlayback();
$('by-frame').onclick=()=>{stop();$('frame').focus();};
for(const [id,step] of [['previous-frame',-1],['next-frame',1]])$(id).onclick=()=>{if(!frames.length)return;stop();current=(current+step+frames.length)%frames.length;draw();};
document.addEventListener('visibilitychange',()=>{if(document.hidden){clearInterval(timer);timer=null;}else if(playbackWanted)startPlayback();});
$('speed').onchange=()=>{if(timer){stop();$('play').click();}};for(const id of ['stretch','invert','reference','palette'])$(id).onchange=draw;
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;stackCache=null;if(mode==='mean'||mode==='trail'){stop();if(!validStack()){status('Choose a valid interval with at least two frames.',true);mode='image';return;}}document.querySelectorAll('[data-mode]').forEach(e=>e.classList.toggle('active',e===b));$('play').disabled=mode==='map';$('aladin').hidden=mode!=='map';$('sky').hidden=mode==='map';$('empty').hidden=true;if(mode==='map'){stop();openMap();}else draw();});
$('gaia').onchange=()=>{if(mode!=='map')document.querySelector('[data-mode="map"]').click();else openMap();};$('survey').onchange=()=>{if(mode==='map')openMap();};
canvas.onclick=e=>{if(!dataset)return;const r=canvas.getBoundingClientRect();point={x:Math.max(0,Math.min(dataset.size-1,Math.floor((e.clientX-r.left)/r.width*dataset.size))),y:Math.max(0,Math.min(dataset.size-1,dataset.size-1-Math.floor((e.clientY-r.top)/r.height*dataset.size)))};draw();drawSpectrum();};
canvas.onkeydown=e=>{if(!dataset)return;point??={x:Math.floor(dataset.size/2),y:Math.floor(dataset.size/2)};const dirs={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]};if(dirs[e.key]){e.preventDefault();point.x=Math.max(0,Math.min(dataset.size-1,point.x+dirs[e.key][0]));point.y=Math.max(0,Math.min(dataset.size-1,point.y+dirs[e.key][1]));draw();drawSpectrum();}};
$('download').onclick=()=>canvas.toBlob(b=>download(b,`spherex-${frames.length?iso(frames[current].mjd):'sky'}.png`));
$('export').onclick=()=>download(new Blob([JSON.stringify(provenance(),null,2)],{type:'application/json'}),'spherex-provenance.json');
$('export-spectrum').onclick=()=>download(new Blob(['wavelength_um,flux_mjy,date,obs_id\n'+spectrumRows.map(r=>[r.wavelength_um,r.flux_mjy,r.date,r.obs_id].join(',')).join('\n')],{type:'text/csv'}),'spherex-spectrum.csv');
$('share').onclick=async()=>{let url;try{url=coordinateURL().href;await navigator.clipboard.writeText(url);status('Coordinate link copied.');}catch(error){status(url||error.message,!url);}};
const gifButton=document.createElement('button');gifButton.textContent='↓ GIF';gifButton.id='gif';$('download').before(gifButton);gifButton.onclick=async()=>{if(!frames.length)return;stop();exportingGif=true;gifButton.disabled=true;const old=current;try{const gif=GIFEncoder();for(let i=0;i<frames.length;i++){current=i;draw();const rgba=ctx.getImageData(0,0,canvas.width,canvas.height).data;const palette=quantize(rgba,128);gif.writeFrame(applyPalette(rgba,palette),canvas.width,canvas.height,{palette,delay:Number($('speed').value),repeat:0});await new Promise(r=>setTimeout(r,0));}gif.finish();download(new Blob([gif.bytes()],{type:'image/gif'}),'spherex-temporal.gif');}catch(e){status(`GIF export failed: ${e.message}`,true);}finally{exportingGif=false;current=old;draw();}};
bandOptions();
const params=new URLSearchParams(location.search);
try{if(params.has('ra')&&params.has('dec')){for(const id of ['ra','dec','fov','detector','collection','start','end'])if(params.has(id))$(id).value=params.get(id);bandOptions();if(params.has('band'))$('band').value=params.get('band');$('fov-label').value=`${$('fov').value}″`;const c=configuration(),example=cfg.targets.find(t=>params.get('example')===t.id&&Math.abs(t.ra-c.ra)<1e-7&&Math.abs(t.dec-c.dec)<1e-7&&t.detector===c.detector);if(example&&!params.has('refresh')&&!params.get('start')&&!params.get('end')&&c.fov===300&&$('band').value==='detector')await loadExample(example);else query();}
else await loadExample(cfg.targets[0]);}catch(error){status(error.message,true);}

function validStack(){const first=Number($('stack-first').value)-1,count=Number($('stack-count').value);return Number.isInteger(first)&&Number.isInteger(count)&&first>=0&&count>=2&&first+count<=frames.length;}
function updateStackRange(){
  const valid=validStack();$('apply-stack').disabled=!valid;stackCache=null;displayLimits.clear();
  const first=Number($('stack-first').value)-1,count=Number($('stack-count').value);
  $('stack-dates').textContent=valid?iso(frames[first].mjd)+' → '+iso(frames[first+count-1].mjd)+' · '+count+' sky-aligned frames':'Select at least two available frames.';
}
for(const id of ['stack-first','stack-count'])$(id).oninput=()=>{updateStackRange();if(validStack()&&(mode==='mean'||mode==='trail'))draw();};
$('apply-stack').onclick=()=>{if(validStack())document.querySelector('[data-mode="trail"]').click();};
$('nav-toggle').onclick=()=>{const open=$('nav-toggle').getAttribute('aria-expanded')!=='true';$('nav-toggle').setAttribute('aria-expanded',String(open));$('navigation').classList.toggle('open',open);};

window.addEventListener('unhandledrejection',event=>{
  if(mode==='map'&&String(event.reason).includes('fetch')){
    event.preventDefault();
    status('A context-map network request failed. The SPHEREx observations are still available under Observations.',true);
  }
});
