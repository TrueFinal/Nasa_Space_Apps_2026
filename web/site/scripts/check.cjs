const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
assert(!html.includes('cdn.tailwindcss.com'), 'Tailwind must be compiled locally');
assert(!html.includes('tailwind.config ='), 'Runtime Tailwind config must be removed');
assert(!html.includes('http://127.0.0.1:'), 'Served homepage must use same-site routes');
const ids = new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]));
for (const match of html.matchAll(/\b(?:src|href)="([^"]+)"/g)) {
  const url = match[1];
  if (url.startsWith('/site-assets/')) assert(fs.statSync(path.join(root, 'assets', url.slice('/site-assets/'.length))).isFile(), `Missing asset ${url}`);
  else if (url.startsWith('#')) assert(ids.has(url.slice(1)), `Missing anchor ${url}`);
  else if (url.startsWith('/')) assert(url === '/lab' || url === '/', `Unknown local route ${url}`);
}
assert.equal([...html.matchAll(/href="\/lab"/g)].length, 3, 'Nav, SPHEREx CTA and Data Explorer must lead to the real lab');
for (const script of html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)) {
  if (script[1].trim()) new vm.Script(script[1], {filename: 'homepage-inline.js'});
}
const logo = fs.readFileSync(path.join(root, 'assets/zephyr-logo.svg'), 'utf8');
assert(logo.includes('viewBox="0 0 1100 620"'));
assert(logo.includes('id="zephyrBeam"'));
assert(logo.includes('M267 672H376L266 753H376'));
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'assets/manifest.json'), 'utf8'));
for (const [name, metadata] of Object.entries(manifest.files)) assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'assets', name))).digest('hex'), metadata.sha256, `Asset changed without rebuilding: ${name}`);
assert(fs.readFileSync(path.join(root, 'assets/home.css'), 'utf8').includes('bg-brand-red'), 'Brand Tailwind utilities must be present');
console.log('Homepage checks passed: local assets, route links, anchors, JavaScript syntax, logo and SHA-256 manifest.');

assert(!html.includes('spherex-canvas'), 'The 3D canvas must not return');
assert(!html.includes('THREE.'), 'The 3D engine must not return');
assert(!html.includes('Independent mission concept'));
assert(html.includes('/site-assets/spherex-cutout.png'));
