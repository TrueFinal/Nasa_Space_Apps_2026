import test from 'node:test';
import assert from 'node:assert/strict';
import { available, cropFor, starsFor, segmentsFor, limitsFor, backgroundFor, imagePoint, pixelAt, viewport, stretch, spectralPoints } from './plate.mjs';

function frame() {
  const image = Array.from({ length: 6 }, (_, y) => Array.from({ length: 8 }, (_, x) => x + y / 10));
  return { shape: [6, 8], image, science: image, masked: image, mask: Array.from({ length: 6 }, () => Array(8).fill(0)),
    gaia: [{ x: 2, y: 2 }, { x: 7, y: 3 }, { x: 1000, y: 1000 }, { x: NaN, y: 2 }],
    plot: { crop: { x: 1, y: 1, w: 4, h: 4 }, full_crop: { x: 0, y: 0, w: 8, h: 6 } } };
}
test('catalogue points must match the actual cropped available pixels', () => {
  const f = frame();
  assert.equal(starsFor(f, 'target').length, 1);
  assert.equal(starsFor(f, 'field').length, 2);
  f.mask[2][2] = 1;
  assert.equal(starsFor(f, 'target').length, 0);
  f.mask[2][2] = 4;
  assert.equal(starsFor(f, 'target', true).length, 0);
  assert.equal(starsFor(f, 'target', false).length, 1);
  assert.equal(starsFor(f, 'target', false, false).length, 0);
});
test('no line bridges a missing point or missing pixels between predictions', () => {
  const f = frame();
  f.trajectory = [{ x: 1, y: 2 }, { x: 9, y: 2 }, { x: 4, y: 2 }];
  assert.deepEqual(segmentsFor(f, 'target').map(s => s.length), [1, 1]);
  f.trajectory = [{ x: 1, y: 2 }, { x: 4, y: 2 }];
  f.mask[2][2] = 1;
  assert.deepEqual(segmentsFor(f, 'target').map(s => s.length), [1, 1]);
});
test('cropped pixel coordinates round trip with inverted Y and preserved image aspect', () => {
  const f = frame(), c = cropFor(f, 'target'), v = viewport(c, 800, 700);
  for (let y = c.y; y < c.y + c.h; y++) for (let x = c.x; x < c.x + c.w; x++) {
    const [px, py] = imagePoint({ x, y }, v);
    assert.deepEqual(pixelAt(px, py, v), { x, y });
  }
  assert.equal(pixelAt(0, 0, v), null);
  const full = viewport(cropFor(f, 'field'), 800, 700);
  assert.equal(full.width / full.height, 8 / 6);
});
test('original and science have separate backgrounds and fixed scales across epochs', () => {
  const f = frame();
  f.image = f.science.map(row => row.map(v => v + 100));
  const limits = limitsFor([f], 'science', 'target');
  const original = limitsFor([f], 'image', 'target');
  assert.deepEqual(limitsFor([f], 'masked', 'target'), limits);
  assert.ok(Math.abs(original.lo - limits.lo) < 1e-12);
  assert.ok(Math.abs(original.hi - limits.hi) < 1e-12);
  assert.ok(Math.abs(backgroundFor(f, 'image', 'target') - backgroundFor(f, 'science', 'target') - 100) < 1e-12);
  assert.ok(stretch(0, limits) >= 0);
  assert.ok(stretch(0, limits) <= 1);
  const other = frame(); other.science[2][2] += 50;
  const pooled = limitsFor([f, other], 'science', 'target');
  assert.ok(pooled.hi > limits.hi);
});
test('invalid crop is clamped to a real image and null pixels are not zero flux', () => {
  const f = frame(); f.plot.crop.x = 900;
  assert.deepEqual(cropFor(f, 'target'), { x: 0, y: 0, w: 8, h: 6 });
  f.science[2][2] = null;
  assert.equal(available(f, { x: 2, y: 2 }), false);
  assert.equal(available(f, { x: Infinity, y: 0 }), false);
});
test('detector contrast excludes different-band backgrounds and noise', () => {
  const a = frame(), b = frame(); a.detector = 1; b.detector = 6;
  b.science = b.science.map(row => row.map(v => v * 1000));
  const expected = limitsFor([a], 'science', 'target');
  assert.deepEqual(limitsFor([a, b], 'science', 'target', .3, 1), expected);
  assert.ok(limitsFor([a, b], 'science', 'target').hi > expected.hi);
});
test('spectrum uses calibrated wavelengths, preserves sparse gaps and never turns null into zero', () => {
  const frames = [
    { detector: 1, utc: '2026-07-20T10:00:00', measurement: { lambda_um: .82, bandwidth_um: .02, flux_ujy: 10, error_ujy: 2 } },
    { detector: 6, utc: '2026-07-21T10:00:00', measurement: { lambda_um: 4.9, bandwidth_um: .04, flux_ujy: 80, error_ujy: 8 } },
    { detector: 4, utc: '2026-07-20T10:00:00', measurement: { lambda_um: 3.4, flux_ujy: null, error_ujy: null } },
  ];
  assert.deepEqual(spectralPoints(frames).map(p => p.x), [.82, 4.9]);
  assert.equal(spectralPoints(frames)[1].bandwidth_um, .04);
  assert.equal(spectralPoints(frames, 'time')[1].x - spectralPoints(frames, 'time')[0].x, 86400000);
});
