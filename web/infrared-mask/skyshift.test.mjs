import test from 'node:test';
import assert from 'node:assert/strict';
import { decode, limits, difference, mean, rgba, sameGrid } from './skyshift-math.mjs';
import { plateRGB, playbackFrames } from './plate.mjs';
import { readFile } from 'node:fs/promises';
import * as math from './skyshift-math.mjs';

test('little endian decoder treats zero as missing, preserves negative physical values', () => {
  const buffer = new ArrayBuffer(8), raw = new DataView(buffer);
  [0, 1, 256, 65535].forEach((v, i) => raw.setUint16(i * 2, v, true));
  const values = decode(buffer, { scale: .5, zero: -1 }, [2, 2]);
  assert.ok(Number.isNaN(values[0]));
  assert.equal(values[1], -.5);
  assert.equal(values[2], 127);
  assert.throws(() => decode(buffer, { scale: 1, zero: 0 }, [3, 3]));
});
test('negative, signed differences and no-data alpha preserve the interpretation', () => {
  assert.deepEqual(plateRGB(0), [237, 240, 239]);
  assert.deepEqual(plateRGB(1), [24, 32, 46]);
  const pixels = rgba(new Float32Array([NaN, -1, 0, 1]), { lo: -1, hi: 1 }, true);
  assert.equal(pixels[3], 0);
  assert.deepEqual([...pixels.slice(4, 7)], [37, 86, 200]);
  assert.deepEqual([...pixels.slice(12, 15)], [207, 35, 56]);
});
test('shared contrast keeps brightness changes and arithmetic respects missing coverage', () => {
  const a = new Float32Array([NaN, 1, 10]), b = new Float32Array([2, NaN, 20]);
  const l = limits([a, b]); assert.ok(l.hi > 19);
  assert.deepEqual([...mean([a, b])], [2, 1, 15]);
  const d = difference(b, a); assert.ok(Number.isNaN(d[0])); assert.equal(d[2], 10);
  assert.equal(sameGrid([{ center: { ra: 1, dec: 0 } }], { ra: 0, dec: 0 }), true);
  assert.equal(sameGrid([{}, { center: { ra: 1, dec: 0 } }], { ra: 0, dec: 0 }), false);
});
test('native automatic playback never alternates detectors or widely separated wavelengths', () => {
  const a = { detector: 1, measurement: { lambda_um: 1 } };
  const b = { detector: 4, measurement: { lambda_um: 3 } };
  const c = { detector: 1, measurement: { lambda_um: 1.005 } };
  const d = { detector: 1, measurement: { lambda_um: 1.05 } };
  assert.deepEqual(playbackFrames([a, b, c, d], a), [a, c]);
});
test('celestial projection preserves north/east orientation and RA wrap', () => {
  const c = { ra: 0, dec: 0 };
  assert.deepEqual(math.project(0, 0, c, [101, 101], 1), { x: 50, y: 50 });
  assert.ok(math.project(1 / 3600, 1 / 3600, c, [101, 101], 1).x < 50);
  assert.ok(math.project(1 / 3600, 1 / 3600, c, [101, 101], 1).y < 50);
  assert.ok(math.project(359.9999, 0, c, [101, 101], 1).x > 50);
  assert.equal(math.project(180, 0, c, [101, 101], 1), null);
});

test('public explorer loads aligned frames, changes view and handles spectrum-only products', async () => {
  const nodes = new Map();
  const context = new Proxy({ createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }) }, { get: (obj, key) => obj[key] ?? (() => {}) });
  const element = () => ({ events: {}, children: [], value: '', checked: true, width: 800, height: 600,
    textContent: '', hidden: true, get options() { return this.children; },
    replaceChildren(...items) { this.children = items; }, getContext() { return context; },
    addEventListener(name, fn) { this.events[name] = fn; } });
  const get = id => { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  get('sky-mode').children = ['blink', 'mean', 'difference'].map(value => ({ value }));
  get('sky-mode').value = 'blink'; get('sky-contrast').value = '.3';
  const star = { slug: 'barnard', name: 'Barnard', sets: [{ file: 'frames.json', clock: 'months' }] };
  const only = { slug: 'only', name: 'Only spectrum', sets: [] };
  const frames = { size: [2, 2], clock: 'months', center: { ra: 0, dec: 0 }, pixel_arcsec: 6.15,
    epochs: [0, 1].map(i => ({ id: String(i), det: 1, scale: .1, zero: -1, data_url: `/bin/${i}`,
      mjd_mid: 60000 + i * 180, um_min: .9, um_max: 1, n_exposures: 2 })) };
  const object = { spectrum: [{ um: 1, flux_ujy: -2, err_ujy: 3, det: 1, saturated: false }] };
  const fetch = async url => ({ ok: true, json: async () => url === '/api/skyshift'
    ? { objects: [star, only], commit: 'abc1234', summary: { candidates: 2 }, analysis: null }
    : { entry: url.includes('slug=only') ? only : star, frames: url.includes('slug=only') ? null : frames, object },
    arrayBuffer: async () => new Uint16Array([0, 1, 2, 3]).buffer });
  const source = (await readFile(new URL('./skyshift.mjs', import.meta.url), 'utf8')).replace(/^import .*;\r?\n/, '');
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  await new AsyncFunction('document', 'fetch', ...Object.keys(math), source)(
    { getElementById: get, createElement: element, addEventListener() {} }, fetch, ...Object.values(math));
  assert.equal(get('sky-loaded').hidden, false);
  assert.equal(get('sky-play').disabled, false);
  assert.match(get('sky-image-note').textContent, /D1/);
  assert.match(get('sky-spectrum-note').textContent, /1 sample/);
  get('sky-mode').value = 'difference'; get('sky-mode').events.input();
  assert.match(get('sky-image-note').textContent, /difference/);
  get('sky-object').value = 'only'; await get('sky-object').events.change();
  assert.equal(get('sky-play').disabled, true);
  assert.match(get('sky-image-note').textContent, /no precomputed public images/);
});
