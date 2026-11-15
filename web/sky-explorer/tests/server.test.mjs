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
