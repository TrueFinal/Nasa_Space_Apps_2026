import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import * as plate from './plate.mjs';

// Exercise the UI against its report contract without browser automation.
// Canvas rasterization and layout still need a visual browser check.
function element(tag = 'div') {
  const context = new Proxy({ createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }) }, { get: (obj, key) => obj[key] ?? (() => {}) });
  return { tag, textContent: '', hidden: true, children: [], dataset: {}, attrs: {}, events: {},
    width: 700, height: 700, value: 0, checked: true,
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(k, fn) { this.events[k] = fn; },
    getContext() { return context; },
    getBoundingClientRect() { return { left: 0, top: 0, width: 700, height: 700 }; },
  };
}
const frame = i => ({ id: `exposure_0${i}`, detector: i ? 6 : 4, source: `file${i}.fits`, utc: `2026-07-22T14:5${i}:00`,
  fits: `files/exposure_0${i}.fits`, shape: [2, 2], image: [[.5, 1], [null, 2]],
  science: [[0, .5], [null, 1.5]], masked: [[0, null], [null, 1.5]], mask: [[64, 4], [1, 32]],
  wavelength: [[3.4, 3.5], [3.4, 3.4]], trajectory: [{ x: .5, y: .5 }],
  target: { x: .5, y: .5, ra: 28, dec: 12 }, gaia: [{ x: 1, y: 1 }],
  measurement: { status: i ? 'masked_aperture' : 'aperture_measurement', flux_ujy: i ? null : 10,
    error_ujy: i ? null : 2, snr: i ? null : 5, coverage: i ? .8 : 1, lambda_um: 3.4, bandwidth_um: .09 },
  calibration: { source: 'CWAVE' }, accepted_fraction: .5, advisory_fraction: .25 });
const source = (await readFile(new URL('./app.js', import.meta.url), 'utf8')).replace(/^import .* from '.\/plate.mjs';\r?\n/, '');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const run = (document, fetch) => new AsyncFunction('document', 'fetch', ...Object.keys(plate), source)(document, fetch, ...Object.values(plate));

test('report renders all image modes, frame navigation, missing measurements and pixel flags', async () => {
  const nodes = new Map(); const get = id => { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  get('query').elements = { low_um: {}, high_um: {}, max_exposures: {}, detector: {} };
  get('tabs').children = ['science', 'masked', 'mask', 'wavelength', 'image'].map(mode => ({ ...element('button'), dataset: { mode } }));
  const report = { synthetic: false, object: '1766', config: { low_um: 3.3, high_um: 3.5, max_exposures: 4, aperture_px: 2 },
    contrast: [0, 2], frames: [frame(0), frame(1)], gaia_status: { status: 'loaded' },
    created_utc: '2026-11-15T12:00:00',
    color_mosaic: { preview: 'files/color_mosaic.png', shape: [8, 8], reference_frame: 'exposure_00',
      complete_rgb_fraction: 0, channels: [{ channel: 'G', coverage_fraction: .5 }],
      contributors: [{ utc: '2026-07-20T12:00:00' }, { utc: '2026-07-25T12:00:00' }] },
    mask_bits: { invalid: 1, outside_band: 4, advisory: 32, target: 64 }, limitations: ['Conditional errors'], provenance: {} };
  const document = { getElementById: get, createElement: element, addEventListener() {} };
  const fetch = async path => ({ ok: true, json: async () => path === '/api/state' ? { has_report: true, archive_ready: true } : report });
  await run(document, fetch);
  assert.equal(get('loaded').hidden, false);
  assert.equal(get('synthetic').hidden, true);
  assert.equal(get('measurements').children.length, 2);
  assert.equal(get('fits').href, '/files/exposure_00.fits');
  assert.equal(get('query').elements.low_um.value, 3.3);
  assert.equal(get('color-mosaic').hidden, false);
  assert.equal(get('color-preview').src, '/files/color_mosaic.png?v=2026-11-15T12%3A00%3A00');
  assert.match(get('color-coverage').textContent, /Complete RGB: 0.0%/);
  assert.match(get('color-coverage').textContent, /2026-07-20T12:00:00 to 2026-07-25T12:00:00/);
  for (const button of get('tabs').children) get('tabs').events.click({ target: button });
  get('time').events.input({ target: { value: '1' } });
  assert.equal(get('fits').href, '/files/exposure_01.fits');
  assert.equal(get('frame-label').textContent, '2 / 2');
  assert.equal(get('metrics').children[2].children[0].textContent, '—');
  get('image').events.mousemove({ currentTarget: get('image'), clientX: 200, clientY: 500 });
  assert.match(get('pixel').textContent, /target/);
  assert.match(get('status').textContent, /loaded/);
  assert.equal(get('band-coverage').children.length, 6);
  get('detector-view').events.change({ target: { value: '6' } });
  assert.equal(get('measurements').children.length, 1);
  assert.equal(get('fits').href, '/files/exposure_01.fits');
  get('detector-view').events.change({ target: { value: '0' } });
  assert.equal(get('measurements').children.length, 2);
  get('full-spectrum').events.click();
  assert.equal(get('query').elements.low_um.value, .75);
  assert.equal(get('query').elements.high_um.value, 5);
  assert.equal(get('query').elements.detector.value, 0);
});

test('connection failure is explicit without inventing a dataset', async () => {
  const nodes = new Map(); const get = id => { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  const document = { getElementById: get, createElement: element, addEventListener() {} };
  await run(document, async () => { throw new Error('offline'); });
  assert.match(get('status').textContent, /offline/);
  assert.equal(get('loaded').hidden, true);
});

test('unavailable Gaia suppresses stale catalogue overlays and shows the reason', async () => {
  const nodes = new Map(); const get = id => { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  get('query').elements = { low_um: {}, high_um: {}, max_exposures: {} };
  const report = { synthetic: false, object: '1766', config: { low_um: 3.3, high_um: 3.5, max_exposures: 4, aperture_px: 2 },
    frames: [frame(0)], gaia_status: { status: 'unavailable' }, mask_bits: {}, limitations: [], provenance: {} };
  const document = { getElementById: get, createElement: element, addEventListener() {} };
  await run(document, async path => ({ ok: true, json: async () => path === '/api/state' ? { has_report: true } : report }));
  assert.equal(get('gaia-overlay').disabled, true);
  assert.equal(get('color-mosaic').hidden, true); // Older reports remain usable.
  assert.equal(get('gaia-notice').hidden, false);
  assert.match(get('plot-note').textContent, /no overlay points/);
});

test('frames with no image at the MPC prediction are excluded from the player', async () => {
  const nodes = new Map(); const get = id => { if (!nodes.has(id)) nodes.set(id, element()); return nodes.get(id); };
  const report = { frames: [{ ...frame(0), plot: { eligible: false } }] };
  const document = { getElementById: get, createElement: element, addEventListener() {} };
  await run(document, async path => ({ ok: true, json: async () => path === '/api/state' ? { has_report: true } : report }));
  assert.equal(get('loaded').hidden, true);
  assert.match(get('status').textContent, /No image/);
});
