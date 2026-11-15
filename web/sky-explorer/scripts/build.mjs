import {readFile,writeFile,mkdir,readdir,copyFile,rm} from 'node:fs/promises';
import {resolve} from 'node:path';
const root=resolve(import.meta.dirname,'..'), assets={};
for(const f of ['index.html','style.css','app.js','astro.js','catalogue.js','help.js','config.json','gifenc.js','gifenc.LICENSE.txt']) {
  const type=f.endsWith('.html')?'text/html;charset=utf-8':f.endsWith('.css')?'text/css':f.endsWith('.json')?'application/json':'text/javascript';
  assets['/'+f]={type,body:await readFile(`${root}/worker/${f}`,'utf8')};
}
for(const f of await readdir(`${root}/worker/samples`).catch(()=>[]))assets['/samples/'+f]={type:'application/json',body:await readFile(`${root}/worker/samples/${f}`,'utf8')};
const source=(await readFile(`${root}/worker/index.js`,'utf8')).replace('const ASSETS = {}; // BUILD_ASSETS','const ASSETS = '+JSON.stringify(assets)+';');
await rm(`${root}/dist`,{recursive:true,force:true});
await mkdir(`${root}/dist/server`,{recursive:true});await mkdir(`${root}/dist/.openai`,{recursive:true});
await writeFile(`${root}/dist/server/index.js`,source);
await copyFile(`${root}/.openai/hosting.json`,`${root}/dist/.openai/hosting.json`);
console.log('Built Worker with',Object.keys(assets).length,'assets;',source.length,'bytes');
