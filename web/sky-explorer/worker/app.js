import {ArchiveBrowser} from './catalogue.js';
import {readFits,projectExposure,coadd,groupEpochs,quantile,parseCoordinate,imageFits} from './astro.js';
import {GIFEncoder,quantize,applyPalette} from './gifenc.js';
const $=id=>document.getElementById(id), cfg=await fetch('/config.json').then(r=>r.json());
let raw=[],groups=[],frames=[],dataset=null,current=0,mode='image',timer=null,controller=null,job=0,aladin=null,spectrumRows=[],point=null,gaiaCatalog=null,gaiaKey='',mapBlob=null;
let catalogueContext=null,displayLimits=new Map();
const archive=new ArchiveBrowser($('catalogue'),openArchiveImage);
const canvas=$('sky'),ctx=canvas.getContext('2d'),mini=document.createElement('canvas'),mc=mini.getContext('2d');
const status=(s,error=false)=>{$('status').textContent=s;$('status').classList.toggle('error',error);};
const iso=mjd=>new Date((mjd-40587)*864e5).toISOString().slice(0,10);
function stop(){if(timer)clearInterval(timer);timer=null;$('play').textContent='▶';$('play').setAttribute('aria-label','Reproduzir animação');}
function download(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function bandOptions(){const old=$('band').value,det=Number($('detector').value);$('band').replaceChildren(new Option('Combinar o detector inteiro','detector'));cfg.channels.forEach((c,i)=>{if(c.DETECTOR===det)$('band').add(new Option(`Canal ${i+1} · ${c.WAVELENGTH.toFixed(3)} µm`,String(i+1)));});if([...$('band').options].some(o=>o.value===old))$('band').value=old;}
function configuration(){return {ra:parseCoordinate($('ra').value,true),dec:parseCoordinate($('dec').value,false),fov:Number($('fov').value),detector:Number($('detector').value),size:Math.max(8,Math.round(Number($('fov').value)/6.2))};}
function coordinateURL(){const c=configuration(),u=new URL(location.href);for(const k of ['ra','dec','fov','detector'])u.searchParams.set(k,c[k]);u.searchParams.set('band',$('band').value);u.searchParams.set('collection',$('collection').value);return u;}
function provenance(){return {app:'SPHEREx Sky Explorer',exported_at:new Date().toISOString(),dataset,mode,reference:Number($('reference').value),frames:frames.map(f=>({date:iso(f.mjd),n_images:f.exposures.length,obs_ids:f.exposures.map(e=>e.obs_id),coverage:f.data.filter(Number.isFinite).length/f.data.length})),exposures:raw.map(({data,variance,...r})=>r),palette:$('palette').value,display:'Shared 1–99.5% limits, optional asinh stretch. Browser TAN-SIP + bilinear resampling; not exact area-overlap.'};}
function dataForFrame(i){
  if(!frames.length)return [];
  if(mode==='mean')return coadd(frames.map(f=>({data:f.data,variance:f.weights.map(w=>w>0?1/w:Infinity)})),dataset.size).data;
  if(mode==='difference'){const ref=frames[Number($('reference').value)||0];return frames[i].data.map((v,j)=>Number.isFinite(v)&&Number.isFinite(ref.data[j])?v-ref.data[j]:null);}
  return frames[i].data;
}
function draw(){
  if(!frames.length)return;
  const f=frames[current],data=dataForFrame(current),size=dataset.size;
  mini.width=mini.height=size;
  const pixels=mc.createImageData(size,size);
  const cacheKey=mode+':'+$('reference').value;
  if(!displayLimits.has(cacheKey)){
    const sample=[],step=Math.max(1,Math.ceil(frames.length*size*size/100000));
    for(let fi=0;fi<frames.length;fi++){const values=mode==='difference'?dataForFrame(fi):frames[fi].data;for(let j=0;j<values.length;j+=step)sample.push(values[j]);}
    let lo=quantile(sample,.01),hi=quantile(sample,.995);
    if(mode==='difference'){hi=Math.max(Math.abs(quantile(sample,.01)),Math.abs(quantile(sample,.99)),1e-8);lo=-hi;}
    if(hi<=lo)hi=lo+1;displayLimits.set(cacheKey,[lo,hi]);
  }
  const [lo,hi]=displayLimits.get(cacheKey);
  let count=0;
  for(let y=0;y<size;y++)for(let x=0;x<size;x++) {
    const v=data[y*size+x],j=((size-1-y)*size+x)*4;
    let rgb=[22,36,49];
    if(v!==null&&Number.isFinite(v)){
      count++;
      if(mode==='difference'){const t=Math.max(-1,Math.min(1,v/hi));rgb=t>0?[30+225*t,35+120*t,42+25*t]:[30+30*-t,35+140*-t,42+213*-t];}
      else{let t=Math.max(0,Math.min(1,(v-lo)/(hi-lo)));if($('stretch').value==='asinh')t=Math.asinh(8*t)/Math.asinh(8);if($('invert').checked)t=1-t;rgb=$('palette').value==='inferno'?cfg.inferno[Math.round(t*255)]:[t*255,t*255,t*255];}
    }
    for(let c=0;c<3;c++)pixels.data[j+c]=rgb[c];pixels.data[j+3]=255;
  }
  mc.putImageData(pixels,0,0);ctx.imageSmoothingEnabled=false;ctx.drawImage(mini,0,0,canvas.width,canvas.height);
  if(point){ctx.strokeStyle='#a6ebd0';ctx.lineWidth=1.5;ctx.beginPath();ctx.arc((point.x+.5)*canvas.width/size,(size-point.y-.5)*canvas.height/size,2*canvas.width/size,0,2*Math.PI);ctx.stroke();}
  ctx.fillStyle='#080d12cc';ctx.fillRect(0,0,canvas.width,27);ctx.fillStyle='#e6eeee';ctx.font='12px monospace';ctx.fillText(`SPHEREx ${dataset.bandLabel} | ${iso(f.mjd)} | ${current+1}/${frames.length}`,10,18);
  $('empty').hidden=count>0;$('frame').value=current;$('frame-label').textContent=`${current+1} / ${frames.length}`;
  $('image-caption').textContent=`${iso(f.mjd)} · ${f.exposures.length} exposições · cobertura ${Math.round(count/data.length*100)}%`;
  [...$('epochs').children].forEach((e,i)=>e.classList.toggle('active',i===current));
  const waves=f.exposures.map(e=>e.wave).filter(Number.isFinite),mask=f.exposures.reduce((s,e)=>s+(e.masked||0),0)/f.exposures.length;
  const info=[['Data inicial',iso(f.exposures[0].mjd)],['Data final',iso(f.exposures.at(-1).mjd)],['Exposições',String(f.exposures.length)],['λ central das exposições',waves.length?`${Math.min(...waves).toFixed(3)}–${Math.max(...waves).toFixed(3)} µm`:'—'],['Pixels rejeitados',`${Math.round(mask*100)}% (média)`],['Unidade','MJy/sr'],['Coleção',dataset.collection],['Cobertura do frame',`${Math.round(count/data.length*100)}%`]];
  $('metadata').replaceChildren();for(const [a,b] of info){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=a;dd.textContent=b;$('metadata').append(dt,dd);}
  $('exposure-links').replaceChildren();for(const e of f.exposures){if(!e.url)continue;const a=document.createElement('a');a.href=e.url;a.textContent=`${e.obs_id} ↗`;a.target='_blank';a.rel='noopener';$('exposure-links').append(a);}
}
function rebuild(){
  stop();displayLimits.clear();if(!dataset)return;
  groups=groupEpochs(raw,$('group').value);frames=groups.map(exposures=>({...coadd(exposures,dataset.size),exposures,mjd:exposures.reduce((s,e)=>s+e.mjd,0)/exposures.length}));
  current=0;$('frame').max=Math.max(0,frames.length-1);$('reference').replaceChildren();$('epochs').replaceChildren();
  frames.forEach((f,i)=>{const date=$('group').value==='individual'?new Date((f.mjd-40587)*864e5).toISOString().slice(0,19):iso(f.mjd);$('reference').add(new Option(date,i));const b=document.createElement('button');b.className='epoch';b.textContent=date;const small=document.createElement('small');small.textContent=`${f.exposures.length} exposições`;b.append(small);b.onclick=()=>{stop();current=i;draw();if(mode==='map')openMap();};$('epochs').append(b);});
  $('source-badge').textContent=dataset.isExample?'EXEMPLO OBSERVADO':'CONSULTA AO ARQUIVO';
  $('target-title').textContent=dataset.title||`${dataset.ra.toFixed(5)}°, ${dataset.dec.toFixed(5)}°`;
  $('irsa').href=`https://irsa.ipac.caltech.edu/applications/spherex/?UserTargetWorldPt=${dataset.ra}%20${dataset.dec}%20eq%20j2000`;
  draw();drawSpectrum();if(mode==='map')openMap();
}
function drawSpectrum(){
  const c=$('spectrum'),cctx=c.getContext('2d');cctx.clearRect(0,0,c.width,c.height);cctx.fillStyle='#93a7b1';cctx.font='13px sans-serif';
  if(!dataset||!raw.length)return;
  const p=point||{x:(dataset.size-1)/2,y:(dataset.size-1)/2};
  const factor=1e9*(dataset.fov/dataset.size/3600*Math.PI/180)**2;
  spectrumRows=[];
  for(const e of raw){let sum=0,n=0,background=[];for(let y=0;y<dataset.size;y++)for(let x=0;x<dataset.size;x++){const d=Math.hypot(x-p.x,y-p.y),v=e.data[y*dataset.size+x];if(v===null||!Number.isFinite(v))continue;if(d<=2){sum+=v;n++;}else if(d>=4&&d<=6)background.push(v);}if(n&&background.length&&Number.isFinite(e.wave))spectrumRows.push({wavelength_um:e.wave,flux_mjy:(sum-quantile(background,.5)*n)*factor,date:iso(e.mjd),obs_id:e.obs_id});}
  spectrumRows.sort((a,b)=>a.wavelength_um-b.wavelength_um);
  if(!spectrumRows.length){cctx.fillText('Sem cobertura espectral na posição selecionada.',40,100);return;}
  const points=spectrumRows,lo=Math.min(...points.map(p=>p.flux_mjy)),hi=Math.max(...points.map(p=>p.flux_mjy));
  const d=cfg.channels.filter(c=>c.DETECTOR===dataset.detector),xmin=d[0]?.WL_MIN||.75,xmax=d.at(-1)?.WL_MAX||5.01;
  cctx.strokeStyle='#344752';cctx.beginPath();cctx.moveTo(55,12);cctx.lineTo(55,180);cctx.lineTo(680,180);cctx.stroke();
  cctx.fillText(`${hi.toPrecision(3)} mJy`,2,25);cctx.fillText(`${lo.toPrecision(3)}`,2,180);cctx.fillText(`${xmin.toFixed(2)} µm`,55,210);cctx.fillText(`${xmax.toFixed(2)} µm`,610,210);
  for(const pt of points){const x=55+(pt.wavelength_um-xmin)/(xmax-xmin)*625,y=170-(pt.flux_mjy-lo)/(hi-lo||1)*145;cctx.fillStyle='#a6ebd0';cctx.beginPath();cctx.arc(x,y,4,0,2*Math.PI);cctx.fill();}
  $('spectrum-note').textContent=`${points.length} medidas nas exposições carregadas. Abertura: 2 pixels; fundo em anel de 4–6 pixels. Épocas misturadas; uso exploratório. Posição ${Math.round(p.x)}, ${Math.round(p.y)}.`;
}
function parseCSV(text){let rows=[],row=[],cell='',quoted=false;for(let i=0;i<text.length;i++){const c=text[i];if(c==='"'){if(quoted&&text[i+1]==='"'){cell+='"';i++;}else quoted=!quoted;}else if(!quoted&&(c===','||c==='\n')){row.push(cell.replace(/\r$/,''));cell='';if(c==='\n'){rows.push(row);row=[];}}else cell+=c;}if(cell||row.length){row.push(cell);rows.push(row);}const keys=rows.shift()||[];return rows.filter(r=>r.length>=keys.length).map(r=>Object.fromEntries(keys.map((k,i)=>[k,r[i]])));}
async function get(url,signal){const r=await fetch(url,{signal});if(!r.ok){let m;try{m=(await r.json()).error;}catch{}throw new Error(m||`HTTP ${r.status}`);}return r;}
async function loadExample(t){
  controller?.abort();const id=++job;stop();$('cancel').hidden=true;$('search-button').disabled=false;$('progress').hidden=true;status(`Abrindo observações reais de ${t.name}…`);
  try{const d=await (await get(`/samples/${t.id}.json`)).json();if(id!==job)return;if(!d.exposures?.length)throw new Error('Exemplo indisponível; use a consulta ao arquivo.');
    $('ra').value=t.ra;$('dec').value=t.dec;$('detector').value=t.detector;$('fov').value=d.fov;$('fov-label').value=`${d.fov}″`;$('band').value='detector';bandOptions();
    catalogueContext={ra:d.ra,dec:d.dec,fov:d.fov,size:d.size,detector:t.detector};
    archive.setRows(d.exposures.map(e=>({obs_id:e.obs_id,date:e.date,t_min:e.mjd,energy_bandpassname:`SPHEREx-D${t.detector}`,collection:d.collection,access_url:e.url})),`Exemplo salvo: somente ${d.exposures.length} arquivos da amostra. Use “Buscar todas as imagens” para consultar a lista atual completa.`);
    raw=d.exposures;dataset={...d,isExample:true,detector:t.detector,title:t.name,bandLabel:`D${t.detector}`,exposures:undefined};point=null;rebuild();
    status(`Exemplo real: ${raw.length} de ${d.archive_count} exposições D${t.detector} do DR1, em ${frames.length} épocas. Seleção salva; consulte os dados atuais para ampliar.${d.errors?.length?` ${d.errors.length} downloads indisponíveis na preparação.`:''}`);
    [...$('targets').children].forEach(b=>b.classList.toggle('active',b.dataset.id===t.id));history.replaceState({},'',coordinateURL());
  }catch(e){status(e.message,true);}
}
async function query(event){
  event?.preventDefault();let c;try{c=configuration();}catch(e){status(e.message,true);return;}
  controller?.abort();controller=new AbortController();const signal=controller.signal,id=++job;stop();$('cancel').hidden=false;$('search-button').disabled=true;$('progress').hidden=false;$('progress').value=0;
  const failures=[];
  try{
    status('Consultando exposições na IRSA…');
    const collection=$('collection').value,collections=collection==='all'?['spherex_dr1','spherex_qr3','spherex_dr1_deep','spherex_qr3_deep']:collection==='both'?['spherex_dr1','spherex_qr3']:[collection];let rows=[];
    for(const col of collections){try{const r=await get(`/api/archive?ra=${c.ra}&dec=${c.dec}&fov=${c.fov}&collection=${col}&refresh=1`,signal);rows.push(...parseCSV(await r.text()).map(r=>({...r,collection:col})));}catch(e){if(signal.aborted)throw e;failures.push(`${col}: ${e.message}`);}}
    if(!rows.length)throw new Error(failures.join(' · ')||'Nenhuma exposição disponível nesta região.');
    catalogueContext={...c};
    archive.setRows(rows,`Consulta ${collections.join(' + ')}: todos os arquivos retornados, dos seis detectores. Nenhum corte por data. ${failures.length?'Atenção: uma coleção falhou; a lista pode estar incompleta.':''}`);
    if($('limit').value==='catalogue'){status(`${archive.rows.length} arquivos listados. Use “Ver” para abrir qualquer imagem. A visualização anterior permanece até você abrir outra imagem.`);return;}
    // DR1 takes precedence where the same exposure/detector is present in QR3.
    const unique=new Map();for(const row of rows)if(row.energy_bandpassname===`SPHEREx-D${c.detector}`&&!unique.has(row.obs_id))unique.set(row.obs_id,row);
    rows=[...unique.values()].sort((a,b)=>Number(a.t_min)-Number(b.t_min));
    const total=rows.length;if(!total)throw new Error('Sem imagens para o detector selecionado nesta região.');
    const max=Number($('limit').value);if($('limit').value!=='all'&&rows.length>max){const indices=Array.from({length:max},(_,i)=>Math.round(i*(rows.length-1)/(max-1)));rows=indices.map(i=>rows[i]);}
    const plane=$('band').value==='detector'?null:cfg.channels[Number($('band').value)-1];const band=plane?{min:plane.WL_MIN,max:plane.WL_MAX}:null;
    const exposures=[];let done=0,next=0;
    async function consume(){while(next<rows.length){const row=rows[next++];if(signal.aborted)throw new DOMException('Cancelado','AbortError');try{
      status(`Transferindo e alinhando ${done+1}/${rows.length} imagens · detector D${c.detector}…`);
      const url=`/api/cutout?url=${encodeURIComponent(row.access_url)}&center=${c.ra},${c.dec}&size=${c.fov/3600}`;
      const r=await get(url,signal),hdus=readFits(await r.arrayBuffer());if(id!==job)return;
      const e=projectExposure(hdus,{...c,band,badMask:cfg.badMask});e.obs_id=row.obs_id;e.url=row.access_url;e.collection=row.collection;exposures.push(e);
    }catch(e){if(signal.aborted)throw e;failures.push(`${row.obs_id}: ${e.message}`);}finally{done++;$('progress').value=done/rows.length;}}}
    await Promise.all(Array.from({length:3},consume));if(id!==job)return;
    if(!exposures.length)throw new Error('Não foi possível baixar imagens. '+failures.slice(0,2).join(' · '));
    raw=exposures;dataset={...c,title:`${c.ra.toFixed(5)}°, ${c.dec.toFixed(5)}°`,bandLabel:plane?`${plane.WAVELENGTH.toFixed(3)} µm · canal ${$('band').value}`:`D${c.detector}`,band,collection,archive_count:total,sampled:rows.length<total,failures};point=null;
    rebuild();history.replaceState({},'',coordinateURL());status(`${raw.length}/${total} exposições disponíveis carregadas · ${frames.length} frames · catálogo com ${archive.rows.length} arquivos dos seis detectores.${rows.length<total?' Limite aplicado; aumente para incluir mais imagens.':''}${failures.length?` ${failures.length} consultas/downloads falharam; veja o relatório.`:''}`);
  }catch(e){if(id===job)status(signal.aborted?'Carregamento cancelado. A visualização anterior foi mantida.':e.message,true);}
  finally{if(id===job){$('cancel').hidden=true;$('search-button').disabled=false;$('progress').hidden=true;}}
}
async function openArchiveImage(row){
  if(!catalogueContext)return;
  controller?.abort();controller=new AbortController();const signal=controller.signal,id=++job;stop();
  $('cancel').hidden=false;$('search-button').disabled=true;
  const detector=Number(row.energy_bandpassname.split('D').at(-1)),c={...catalogueContext,detector};
  try{
    status(`Abrindo ${row.obs_id} · D${detector}…`);
    const url=`/api/cutout?url=${encodeURIComponent(row.access_url)}&center=${c.ra},${c.dec}&size=${c.fov/3600}`;
    const response=await get(url,signal),e=projectExposure(readFits(await response.arrayBuffer()),{...c,badMask:cfg.badMask,band:null});
    if(id!==job)return;
    e.obs_id=row.obs_id;e.url=row.access_url;e.collection=row.collection;raw=[e];
    dataset={...c,collection:row.collection,title:row.obs_id,bandLabel:`D${detector}`,archive_count:archive.rows.length};point=null;
    rebuild();status(`Imagem individual ${row.obs_id} · ${row.collection}. Todos os outros arquivos continuam na lista.`);
  }catch(e){if(id===job)status(signal.aborted?'Abertura cancelada.':e.message,true);}
  finally{if(id===job){$('cancel').hidden=true;$('search-button').disabled=false;$('progress').hidden=true;}}
}
async function openMap(){
  if(!dataset)return;
  try{const {default:A}=await import('https://cdn.jsdelivr.net/npm/aladin-lite@3.9.2-beta/dist/aladin.js');await A.init;
    if(!aladin)aladin=A.aladin('#aladin',{survey:$('survey').value,fov:dataset.fov/3600,target:`${dataset.ra} ${dataset.dec}`});
    aladin.gotoRaDec(dataset.ra,dataset.dec);aladin.setFoV(dataset.fov/3600);aladin.setImageSurvey($('survey').value);
    if(mapBlob)URL.revokeObjectURL(mapBlob);
    mapBlob=URL.createObjectURL(new Blob([imageFits(frames[current].data,dataset)],{type:'application/fits'}));
    aladin.displayFITS(mapBlob,{opacity:.7},()=>{},()=>status('Não foi possível sobrepor o frame SPHEREx no mapa.',true),'SPHEREx • época atual');
    const key=`${dataset.ra},${dataset.dec},${dataset.fov}`;
    if(gaiaKey!==key){gaiaCatalog?.hide();gaiaCatalog=null;gaiaKey=key;}
    if($('gaia').checked){
      gaiaCatalog?.hide();
      const response=await get(`/api/gaia?ra=${dataset.ra}&dec=${dataset.dec}&fov=${dataset.fov}`);
      const table=await response.json(),names=(table.metadata||table.columns).map(c=>c.name),year=2000+(frames[current].mjd-51544.5)/365.25;
      const sources=table.data.map(row=>{const r=Object.fromEntries(names.map((n,i)=>[n,row[i]]));const dt=year-(r.ref_epoch||2016);return A.source(r.ra+(r.pmra||0)*dt/3600000/Math.cos(r.dec*Math.PI/180),r.dec+(r.pmdec||0)*dt/3600000,{catalog:'Gaia DR3 / GAVO',G:r.phot_g_mean_mag,epoch:year.toFixed(2)});});
      gaiaCatalog=A.catalog({name:'Gaia DR3 • movimento próprio linear',color:'#a6ebd0',sourceSize:9,onClick:'showTable'});gaiaCatalog.addSources(sources);aladin.addCatalog(gaiaCatalog);
    }
    else gaiaCatalog?.hide();
  }catch(e){status(e.message,true);}
}
for(const t of cfg.targets){const b=document.createElement('button');b.type='button';b.className='target';b.dataset.id=t.id;b.textContent=t.name;const s=document.createElement('span');s.textContent=t.description;b.append(s);b.onclick=()=>loadExample(t);$('targets').append(b);}
$('search').onsubmit=query;$('load-all').onclick=()=>{$('limit').value='all';$('collection').value='all';query();};$('cancel').onclick=()=>controller?.abort();$('fov').oninput=()=>{$('fov-label').value=`${$('fov').value}″`;};$('detector').onchange=bandOptions;
$('band').onchange=()=>{$('band-help').textContent=$('band').value==='detector'?'Faixa ampla: cobertura espectral variável. Clique em explorar para aplicar.':'Canal fixo: pixels fora da faixa são mascarados em todas as épocas. Clique em explorar para aplicar.';};
$('group').onchange=rebuild;$('frame').oninput=()=>{stop();current=Number($('frame').value);draw();if(mode==='map')openMap();};
$('play').onclick=()=>{if(timer){stop();return;}if(frames.length<2)return;$('play').textContent='Ⅱ';$('play').setAttribute('aria-label','Pausar');timer=setInterval(()=>{current=(current+1)%frames.length;draw();},Number($('speed').value));};
$('speed').onchange=()=>{if(timer){stop();$('play').click();}};for(const id of ['stretch','invert','reference','palette'])$(id).onchange=draw;
document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;document.querySelectorAll('[data-mode]').forEach(e=>e.classList.toggle('active',e===b));$('play').disabled=mode==='map';$('aladin').hidden=mode!=='map';$('sky').hidden=mode==='map';$('empty').hidden=true;if(mode==='map'){stop();openMap();}else draw();});
$('gaia').onchange=()=>{if(mode!=='map')document.querySelector('[data-mode="map"]').click();else openMap();};$('survey').onchange=()=>{if(mode==='map')openMap();};
canvas.onclick=e=>{if(!dataset)return;const r=canvas.getBoundingClientRect();point={x:Math.max(0,Math.min(dataset.size-1,Math.floor((e.clientX-r.left)/r.width*dataset.size))),y:Math.max(0,Math.min(dataset.size-1,dataset.size-1-Math.floor((e.clientY-r.top)/r.height*dataset.size)))};draw();drawSpectrum();};
canvas.onkeydown=e=>{if(!dataset)return;point??={x:Math.floor(dataset.size/2),y:Math.floor(dataset.size/2)};const dirs={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,1],ArrowDown:[0,-1]};if(dirs[e.key]){e.preventDefault();point.x=Math.max(0,Math.min(dataset.size-1,point.x+dirs[e.key][0]));point.y=Math.max(0,Math.min(dataset.size-1,point.y+dirs[e.key][1]));draw();drawSpectrum();}};
$('download').onclick=()=>canvas.toBlob(b=>download(b,`spherex-${frames.length?iso(frames[current].mjd):'sky'}.png`));
$('export').onclick=()=>download(new Blob([JSON.stringify(provenance(),null,2)],{type:'application/json'}),'spherex-provenance.json');
$('export-spectrum').onclick=()=>download(new Blob(['wavelength_um,flux_mjy,date,obs_id\n'+spectrumRows.map(r=>[r.wavelength_um,r.flux_mjy,r.date,r.obs_id].join(',')).join('\n')],{type:'text/csv'}),'spherex-spectrum.csv');
$('share').onclick=async()=>{try{await navigator.clipboard.writeText(coordinateURL().href);status('Link da região copiado.');}catch{status(coordinateURL().href);}};
const gifButton=document.createElement('button');gifButton.textContent='↓ GIF';gifButton.id='gif';$('download').before(gifButton);gifButton.onclick=async()=>{if(!frames.length)return;stop();gifButton.disabled=true;const old=current;try{const gif=GIFEncoder();for(let i=0;i<frames.length;i++){current=i;draw();const rgba=ctx.getImageData(0,0,canvas.width,canvas.height).data;const palette=quantize(rgba,128);gif.writeFrame(applyPalette(rgba,palette),canvas.width,canvas.height,{palette,delay:Number($('speed').value),repeat:0});await new Promise(r=>setTimeout(r,0));}gif.finish();download(new Blob([gif.bytes()],{type:'image/gif'}),'spherex-temporal.gif');}catch(e){status(`Não foi possível exportar o GIF: ${e.message}`,true);}finally{current=old;draw();gifButton.disabled=false;}};
bandOptions();
const params=new URLSearchParams(location.search);
if(params.has('ra')&&params.has('dec')){for(const id of ['ra','dec','fov','detector','collection'])if(params.has(id))$(id).value=params.get(id);bandOptions();if(params.has('band'))$('band').value=params.get('band');$('fov-label').value=`${$('fov').value}″`;query();}
else await loadExample(cfg.targets[0]);
