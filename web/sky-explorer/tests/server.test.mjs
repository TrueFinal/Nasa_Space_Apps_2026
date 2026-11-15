import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../dist/server/index.js';
test('public application assets and prepared observed examples are served',async()=>{
 for(const path of ['/','/astro.js','/config.json','/gifenc.js','/samples/wise0855.json']){const r=await worker.fetch(new Request('http://test'+path));assert.equal(r.status,200,path);}
 const r=await worker.fetch(new Request('http://test/samples/wise0855.json'));const d=await r.json();assert.ok(d.exposures.length>=2);assert.equal(d.target.id,'wise0855');
});
test('archive input validation and FITS allowlist reject invalid requests before network access',async()=>{
 for(const path of ['/api/archive?ra=360&dec=0','/api/archive?ra=0&dec=91','/api/archive?ra=1&dec=1&fov=99999','/api/archive?ra=1&dec=1&collection=private','/api/cutout?url=https://example.com/data.fits']){const r=await worker.fetch(new Request('http://test'+path));assert.equal(r.status,400,path);}
});
test('live archive still works when hosting denies the default Cache API',async()=>{
 const original=globalThis.fetch,descriptor=Object.getOwnPropertyDescriptor(globalThis,'caches');
 try{
  Object.defineProperty(globalThis,'caches',{configurable:true,get(){throw new Error('This Worker is not permitted to access the default cache.');}});
  globalThis.fetch=async()=>new Response('s_ra,s_dec\n1,2\n');
  const r=await worker.fetch(new Request('http://test/api/archive?ra=1&dec=2&fov=300'));
  assert.equal(r.status,200);assert.match(await r.text(),/s_ra,s_dec/);
 }finally{globalThis.fetch=original;if(descriptor)Object.defineProperty(globalThis,'caches',descriptor);else delete globalThis.caches;}
});
test('IRSA transient errors retry through the official alternate host',async()=>{
 const original=globalThis.fetch;const hosts=[];
 try{
  globalThis.fetch=async(url)=>{hosts.push(new URL(url).hostname);return hosts.length===1?new Response('temporary outage',{status:502}):new Response('s_ra,s_dec\n1,2\n');};
  const r=await worker.fetch(new Request('http://test/api/archive?ra=1&dec=2&fov=300'));
  assert.equal(r.status,200);assert.deepEqual(hosts,['irsa.ipac.caltech.edu','irsaproxy1.ipac.caltech.edu']);
 }finally{globalThis.fetch=original;}
});

test('UTC date interval is forwarded to SIA as inclusive MJD time',async()=>{
 const original=globalThis.fetch;let upstream;
 try{globalThis.fetch=async url=>{upstream=new URL(url);return new Response('obs_id\n');};
 const res=await worker.fetch(new Request('http://test/api/archive?ra=133.795&dec=-7.245&fov=300&collection=spherex_dr1&start=2025-05-01&end=2026-05-31'));
 assert.equal(res.status,200);assert.match(upstream.searchParams.get('TIME'),/^60796 /);
 }finally{globalThis.fetch=original;}
});

test('home and laboratory remain distinct and home assets are bundled',async()=>{
 const home=await worker.fetch(new Request('http://test/'));
 assert.match(await home.text(),/id="hero"/);
 const lab=await worker.fetch(new Request('http://test/lab'));
 assert.match(await lab.text(),/id="ra"/);
 const image=await worker.fetch(new Request('http://test/site-assets/spherex-cutout.png'));
 assert.equal(image.headers.get('content-type'),'image/png');
 assert.deepEqual([...new Uint8Array(await image.arrayBuffer()).slice(0,4)],[137,80,78,71]);
});
