import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {readFits,worldPixel,wavelengthMap,coadd,groupEpochs,parseCoordinate,projectExposure} from '../worker/astro.js';
const bytes=await readFile(new URL('./fixtures/spherex_cutout.fits',import.meta.url));
const hdus=readFits(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
const ref=JSON.parse(await readFile(new URL('./fixtures/astropy-reference.json',import.meta.url)));
test('TAN-SIP inversion agrees with independent Astropy values on real IRSA cutout',()=>{
 const image=hdus.find(h=>h.header.EXTNAME==='IMAGE');
 for(const p of ref.positions){const [x,y]=worldPixel(image.header,p.ra,p.dec);assert.ok(Math.abs(x-p.x)<1e-4);assert.ok(Math.abs(y-p.y)<1e-4);}
 assert.equal(image.data.length,29*29);
});
test('real spectral lookup and projected cutout have finite data',()=>{
 const wave=wavelengthMap(hdus)(14,14);assert.ok(wave>4.8&&wave<4.9);
 const out=projectExposure(hdus,{ra:133.786245,dec:-7.244372,fov:176,size:28,badMask:4292870143});
 assert.ok(out.data.filter(Number.isFinite).length>650);
 assert.ok(Math.abs(out.wave-4.860666907)<1e-5);
 const absent=projectExposure(hdus,{ra:133.786245,dec:-7.244372,fov:176,size:28,badMask:4292870143,band:{min:1,max:1.1}});
 assert.ok(absent.data.every(v=>!Number.isFinite(v)));
});
test('coaddition respects variance and missing pixels rather than filling missing sky with zero',()=>{
 const r=coadd([{data:[10,null,4,NaN],variance:[1,1,1,1]},{data:[20,null,6,8],variance:[4,1,1,4]}],2);
 assert.equal(r.data[0],12);assert.equal(r.data[1],null);assert.equal(r.data[2],5);assert.equal(r.data[3],8);assert.deepEqual(r.hits,[2,0,2,1]);
});
test('time grouping keeps later partial surveys and never uses wavelengths as epochs',()=>{
 const rows=[{mjd:60800,wave:4.8},{mjd:60801,wave:4.9},{mjd:61000,wave:4.8},{mjd:61160,wave:4.8}];
 assert.deepEqual(groupEpochs(rows).map(g=>g.length),[2,1,1]);
 assert.equal(groupEpochs(rows,'semester').flat().length,4);
});
test('decimal and sexagesimal coordinates handle negative zero and invalid ranges',()=>{
 assert.ok(Math.abs(parseCoordinate('08h55m10.831s',true)-133.7951291667)<1e-8);
 assert.ok(Math.abs(parseCoordinate('-00:30:00',false)+.5)<1e-10);
 assert.throws(()=>parseCoordinate('360',true));assert.throws(()=>parseCoordinate('-91',false));assert.throws(()=>parseCoordinate('',true));
});
