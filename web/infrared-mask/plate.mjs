// Native image geometry. Display-only equivalents of SkyShift's crop/plate policy.
export function cropFor(frame, scope = 'target') {
  const [h, w] = frame.shape;
  const c = scope === 'field' ? frame.plot?.full_crop : frame.plot?.crop;
  if (!c || ![c.x, c.y, c.w, c.h].every(Number.isInteger)
      || c.x < 0 || c.y < 0 || c.w <= 0 || c.h <= 0 || c.x + c.w > w || c.y + c.h > h) {
    return { x: 0, y: 0, w, h };
  }
  return c;
}
export function available(frame, p, crop = cropFor(frame, 'field'), band = false) {
  if (!Number.isFinite(p.x) || !Number.isFinite(p.y)) return false;
  if (p.x < crop.x - .5 || p.y < crop.y - .5
      || p.x >= crop.x + crop.w - .5 || p.y >= crop.y + crop.h - .5) return false;
  const x = Math.floor(p.x + .5), y = Math.floor(p.y + .5);
  const value = frame.science?.[y]?.[x];
  return value != null && Number.isFinite(value) && !(frame.mask[y][x] & (1 | 2 | 16 | (band ? 4 : 0)));
}
export function starsFor(frame, scope, band = false, enabled = true) {
  if (!enabled) return [];
  const crop = cropFor(frame, scope);
  const stars = scope === 'field' ? frame.plot?.field_gaia : frame.plot?.gaia;
  return (stars || frame.gaia || []).filter(p => available(frame, p, crop, band));
}
export function segmentsFor(frame, scope, band = false) {
  const crop = cropFor(frame, scope);
  const groups = (scope === 'field' ? frame.plot?.field_trajectory_segments : frame.plot?.trajectory_segments)
    || [frame.trajectory || []];
  const output = [];
  for (const group of groups) {
    let segment = [];
    for (const p of group) {
      if (!available(frame, p, crop, band)) { if (segment.length) output.push(segment); segment = []; continue; }
      if (segment.length) {
        const previous = segment.at(-1), n = Math.max(2, Math.ceil(Math.hypot(p.x - previous.x, p.y - previous.y) * 2));
        let gap = false;
        for (let i = 1; i < n; i++) {
          if (!available(frame, { x: previous.x + (p.x - previous.x) * i / n, y: previous.y + (p.y - previous.y) * i / n }, crop, band)) { gap = true; break; }
        }
        if (gap) { output.push(segment); segment = []; }
      }
      segment.push(p);
    }
    if (segment.length) output.push(segment);
  }
  return output;
}
function percentile(sorted, p) {
  if (!sorted.length) return 0;
  const r = (sorted.length - 1) * p / 100, i = Math.floor(r), f = r - i;
  return sorted[i] * (1 - f) + sorted[Math.min(i + 1, sorted.length - 1)] * f;
}
export function backgroundFor(frame, mode, scope) {
  const key = mode === 'image' ? 'image' : 'science';
  const meta = scope === 'field' ? frame.plot?.field_background : frame.plot?.background;
  if (Number.isFinite(meta?.[key])) return meta[key];
  const c = cropFor(frame, scope), vals = [];
  for (let y = c.y; y < c.y + c.h; y++) for (let x = c.x; x < c.x + c.w; x++) {
    const v = frame[key][y][x];
    if (v != null && Number.isFinite(v) && available(frame, { x, y }, c)) vals.push(v);
  }
  return percentile(vals.sort((a, b) => a - b), 50);
}
const limitsCache = new WeakMap();
export function limitsFor(frames, mode, scope, contrast = .3, detector) {
  // Applying a mask must not change the brightness scale of the surviving pixels.
  const sourceMode = mode === 'masked' ? 'science' : mode;
  const key = JSON.stringify([sourceMode, scope, contrast, detector]);
  let cache = limitsCache.get(frames);
  if (!cache) { cache = new Map(); limitsCache.set(frames, cache); }
  if (cache.has(key)) return cache.get(key);
  const c = Math.max(0, Math.min(1, contrast));
  const pLo = .5 + 9.5 * c, pHi = 100 - .05 * 10 ** (2.3 * c), values = [];
  for (const frame of frames) {
    if (detector != null && frame.detector !== detector) continue;
    const crop = cropFor(frame, scope), background = backgroundFor(frame, sourceMode, scope);
    for (let y = crop.y; y < crop.y + crop.h; y++) for (let x = crop.x; x < crop.x + crop.w; x++) {
      const value = frame[sourceMode][y][x];
      if (value != null && Number.isFinite(value) && available(frame, { x, y }, crop)) values.push(value - background);
    }
  }
  values.sort((a, b) => a - b);
  const lo = percentile(values, pLo), hi = percentile(values, pHi);
  const result = { lo, hi: hi > lo ? hi : lo + (Math.abs(lo) || 1) * .001, pLo, pHi };
  cache.set(key, result);
  return result;
}
export function spectralPoints(frames, axis = 'spectrum') {
  return frames.map((frame, i) => ({ ...frame.measurement, i, detector: frame.detector,
    x: axis === 'time' ? Date.parse(`${frame.utc}Z`) : frame.measurement?.lambda_um }))
    .filter(p => Number.isFinite(p.x) && Number.isFinite(p.flux_ujy) && Number.isFinite(p.error_ujy));
}
export function stretch(value, limits) {
  const t = Math.max(0, Math.min(1, (value - limits.lo) / (limits.hi - limits.lo)));
  return Math.log1p(1000 * t) / Math.log1p(1000);
}
export function viewport(crop, width, height) {
  const scale = Math.min((width - 80) / crop.w, (height - 90) / crop.h);
  return { left: 50 + (width - 80 - crop.w * scale) / 2, top: 20 + (height - 90 - crop.h * scale) / 2,
    width: crop.w * scale, height: crop.h * scale, scale, crop };
}
export function imagePoint(p, view) {
  return [view.left + (p.x - view.crop.x + .5) * view.scale,
    view.top + (view.crop.y + view.crop.h - .5 - p.y) * view.scale];
}
export function pixelAt(px, py, view) {
  if (px < view.left || py < view.top || px >= view.left + view.width || py >= view.top + view.height) return null;
  return { x: view.crop.x + Math.floor((px - view.left) / view.scale),
    y: view.crop.y + view.crop.h - 1 - Math.floor((py - view.top) / view.scale) };
}
