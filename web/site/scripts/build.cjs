const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const asset = path.join(root, 'assets');
fs.mkdirSync(asset, {recursive: true});
const manifest = {
  tailwindVersion: '3.4.17',
  files: {},
};
for (const [source, output, upstream] of [
  ['tailwindcss/LICENSE', 'tailwind-LICENSE.txt', 'https://github.com/tailwindlabs/tailwindcss/blob/v3.4.17/LICENSE'],
]) {
  const content = fs.readFileSync(path.join(root, 'node_modules', source));
  fs.writeFileSync(path.join(asset, output), content);
  manifest.files[output] = {upstream, sha256: crypto.createHash('sha256').update(content).digest('hex')};
}
execFileSync(process.execPath, [path.join(root, 'node_modules/tailwindcss/lib/cli.js'), '--config', 'tailwind.config.cjs', '--input', 'input.css', '--output', 'assets/home.css', '--minify'], {cwd: root, stdio: 'inherit'});
for (const name of ['home.css', 'theme.css', 'zephyr-logo.svg', 'spherex-cutout.png']) {
  manifest.files[name] = {sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(asset, name))).digest('hex')};
}
fs.writeFileSync(path.join(asset, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n');
require('./check.cjs');
