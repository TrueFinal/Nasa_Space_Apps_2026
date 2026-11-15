// SkyShift contracts/api.md and blink/{math,paint}.ts, Apache-2.0; see docs/skyshift.md.
import { stretch, plateRGB } from './plate.mjs';

export function decode(buffer, epoch, size) {
  const n = size[0] * size[1];
  if (buffer.byteLength !== 2 * n || !Number.isFinite(epoch.scale) || !Number.isFinite(epoch.zero)) throw new Error('Invalid reference image');
  const input = new DataView(buffer), out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const raw = input.getUint16(i * 2, true);
    out[i] = raw ? raw * epoch.scale + epoch.zero : NaN;
  }
  return out;
}
function percentile(sorted, p) {
  const r = (sorted.length - 1) * p / 100, i = Math.floor(r), f = r - i;
  return sorted[i] * (1 - f) + sorted[Math.min(i + 1, sorted.length - 1)] * f;
}
export function median(values) {
  const sample = Array.from(values).filter(Number.isFinite).sort((a, b) => a - b);
  return sample.length ? percentile(sample, 50) : 0;
}
export function limits(frames, contrast = .3) {
  const stride = Math.max(1, Math.ceil(frames.reduce((n, f) => n + f.length, 0) / 200000));
  const values = [];
  for (const frame of frames) for (let i = 0; i < frame.length; i += stride) if (Number.isFinite(frame[i])) values.push(frame[i]);
  values.sort((a, b) => a - b);
  if (!values.length) return { lo: 0, hi: 1 };
  const c = Math.max(0, Math.min(1, contrast));
  const lo = percentile(values, .5 + 9.5 * c), hi = percentile(values, 100 - .05 * 10 ** (2.3 * c));
  return { lo, hi: hi > lo ? hi : lo + (Math.abs(lo) || 1) * .001 };
}
export function difference(current, reference) {
  if (current.length !== reference.length) throw new Error('Different grids');
  return current.map((v, i) => v - reference[i]);
}
export function mean(frames) {
  return frames[0].map((_, i) => {
    let sum = 0, n = 0;
    for (const f of frames) if (Number.isFinite(f[i])) { sum += f[i]; n++; }
    return n ? sum / n : NaN;
  });
}
export function sameGrid(epochs, center) {
  const first = epochs[0]?.center || center;
  return epochs.every(e => Math.abs((e.center || center).ra - first.ra) < 1e-9
    && Math.abs((e.center || center).dec - first.dec) < 1e-9);
}
export function project(ra, dec, center, size, pixelArcsec) {
  // Exact TAN projection for the public grid (both axes negative, row zero north).
  const r = Math.PI / 180, a = ra * r, d = dec * r, a0 = center.ra * r, d0 = center.dec * r;
  const den = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a - a0);
  if (!(den > 0)) return null;
  const east = Math.cos(d) * Math.sin(a - a0) / den / r * 3600;
  const north = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a - a0)) / den / r * 3600;
  const x = (size[0] - 1) / 2 - east / pixelArcsec, y = (size[1] - 1) / 2 - north / pixelArcsec;
  return Number.isFinite(x) && Number.isFinite(y) && x >= -.5 && y >= -.5 && x < size[0] - .5 && y < size[1] - .5 ? { x, y } : null;
}
export function rgba(values, lim, signed = false) {
  const out = new Uint8ClampedArray(values.length * 4);
  const span = Math.max(Math.abs(lim.lo), Math.abs(lim.hi), 1e-12);
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    if (!Number.isFinite(v)) continue;
    let rgb;
    if (signed) {
      const t = Math.min(1, Math.abs(v) / span), target = v < 0 ? [37, 86, 200] : [207, 35, 56];
      rgb = [237, 240, 239].map((x, k) => Math.round(x + (target[k] - x) * t));
    } else rgb = plateRGB(stretch(v, lim));
    out.set([...rgb, 255], i * 4);
  }
  return out;
}
