// Assets are embedded by scripts/build.mjs; science runs locally in the browser.
const ASSETS = {}; // BUILD_ASSETS
const ALLOWED = new Set(['spherex_dr1','spherex_qr3','spherex_dr1_deep','spherex_qr3_deep','spherex_dr1_cube']);
const json=(data,status=200)=>new Response(JSON.stringify(data),{status,headers:{'content-type':'application/json;charset=utf-8'}});
export default {
  async fetch(request,env,ctx) {
    const u=new URL(request.url);
    if(request.method!=='GET')return json({error:'Método não permitido'},405);
    try {
      let upstream,ttl=600;
      if(u.pathname==='/api/archive') {
        const ra=Number(u.searchParams.get('ra')),dec=Number(u.searchParams.get('dec')),fov=Number(u.searchParams.get('fov')||300),collection=u.searchParams.get('collection')||'spherex_dr1';
        if(!u.searchParams.has('ra')||!u.searchParams.has('dec')||!Number.isFinite(ra)||!Number.isFinite(dec)||ra<0||ra>=360||Math.abs(dec)>90||!Number.isFinite(fov)||fov<30||fov>1200||!ALLOWED.has(collection))return json({error:'Coordenadas, campo (30–1200″) ou coleção inválidos.'},400);
        upstream=new URL('https://irsa.ipac.caltech.edu/SIA');
        upstream.searchParams.set('COLLECTION',collection);
        upstream.searchParams.set('POS',`CIRCLE ${ra} ${dec} ${fov/7200}`);
        upstream.searchParams.set('RESPONSEFORMAT','CSV');
        if(u.searchParams.get('start')||u.searchParams.get('end')){
          const start=u.searchParams.get('start')||'2025-03-01',end=u.searchParams.get('end')||new Date().toISOString().slice(0,10);
          const a=Date.parse(start+'T00:00:00Z'),b=Date.parse(end+'T00:00:00Z');
          if(!/^\d{4}-\d{2}-\d{2}$/.test(start)||!/^\d{4}-\d{2}-\d{2}$/.test(end)||!Number.isFinite(a+b)||b<a)return json({error:'Invalid UTC date interval.'},400);
          upstream.searchParams.set('TIME',`${a/864e5+40587} ${b/864e5+40588}`);
        }
      } else if(u.pathname==='/api/gaia') {
        const ra=Number(u.searchParams.get('ra')),dec=Number(u.searchParams.get('dec')),fov=Number(u.searchParams.get('fov'));
        if(!u.searchParams.has('ra')||!u.searchParams.has('dec')||!Number.isFinite(ra)||!Number.isFinite(dec)||ra<0||ra>=360||Math.abs(dec)>90||!Number.isFinite(fov)||fov<30||fov>1200)return json({error:'Coordenadas Gaia inválidas.'},400);
        upstream=new URL('https://dc.g-vo.org/tap/sync');ttl=86400;
        const query=`SELECT TOP 2000 ra,dec,2016.0 AS ref_epoch,pmra,pmdec,phot_g_mean_mag FROM gaia.dr3lite WHERE 1=CONTAINS(POINT('ICRS',ra,dec),CIRCLE('ICRS',${ra},${dec},${fov/7200+.05})) ORDER BY phot_g_mean_mag ASC`;
        upstream.search=new URLSearchParams({REQUEST:'doQuery',LANG:'ADQL',FORMAT:'json',QUERY:query}).toString();
      } else if(u.pathname==='/api/cutout') {
        upstream=new URL(u.searchParams.get('url')||'');ttl=86400*7;
        if(upstream.origin!=='https://irsa.ipac.caltech.edu'||!upstream.pathname.startsWith('/ibe/data/spherex/')||!upstream.pathname.endsWith('.fits'))return json({error:'Somente FITS SPHEREx da IRSA são permitidos.'},400);
        const center=u.searchParams.get('center')||'',size=Number(u.searchParams.get('size'));
        if(!/^[-+\d.]+,[-+\d.]+$/.test(center)||!Number.isFinite(size)||size<30/3600||size>1200/3600)return json({error:'Recorte inválido.'},400);
        upstream.search='';upstream.searchParams.set('center',center);upstream.searchParams.set('size',size.toFixed(6));
      } else if(u.pathname==='/health')return json({ok:true,source:'IRSA',version:'1.0.0'});
      else {
        const path=['/','/index.html'].includes(u.pathname)?'/home.html':['/lab','/lab/','/sky','/sky/'].includes(u.pathname)?'/index.html':u.pathname;
        const asset=ASSETS[path];
        if(!asset)return json({error:'Não encontrado'},404);
        return new Response(asset.binary?Uint8Array.from(atob(asset.body),c=>c.charCodeAt(0)):asset.body,{headers:{'content-type':asset.type,'cache-control':path.endsWith('.json')?'public,max-age=300':'public,max-age=600','x-content-type-options':'nosniff','referrer-policy':'strict-origin-when-cross-origin'}});
      }
      const key=new Request(upstream.toString());
      // Some managed Worker runtimes prohibit Cache API access. Caching must
      // remain optional: never prevent a scientific query because of it.
      let cache=null;
      try{cache=globalThis.caches?.default;}catch{}
      if(!u.searchParams.has('refresh')&&cache){try{const hit=await cache.match(key);if(hit)return hit;}catch{cache=null;}}
      let response,lastError;
      for(let attempt=0;attempt<2;attempt++) {
        const endpoint=new URL(upstream);
        if(attempt===1&&endpoint.hostname==='irsa.ipac.caltech.edu')endpoint.hostname='irsaproxy1.ipac.caltech.edu';
        try{
          response=await fetch(endpoint,{signal:AbortSignal.timeout(attempt?25000:20000),redirect:'follow'});
          if(response.ok||response.status<500)break;
        }catch(error){lastError=error;}
      }
      if(!response)throw lastError||new Error('Serviço indisponível');
      if(!response.ok)return json({error:`IRSA respondeu HTTP ${response.status}. Tente novamente ou abra um exemplo salvo.`},502);
      const result=new Response(response.body,{headers:{'content-type':u.pathname==='/api/archive'?'text/csv;charset=utf-8':u.pathname==='/api/gaia'?'application/json':'application/fits','cache-control':`public,max-age=${ttl}`,'x-data-source':u.pathname==='/api/gaia'?'ESA Gaia DR3':'NASA/IPAC IRSA'}});
      if(cache&&ctx?.waitUntil)ctx.waitUntil(cache.put(key,result.clone()).catch(()=>{}));
      return result;
    } catch(error){return json({error:`Falha ao consultar IRSA: ${error.name==='TimeoutError'?'tempo limite':error.message}`},502);}
  }
};
