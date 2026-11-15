import { decode, median, limits, difference, mean, rgba, sameGrid, project } from './skyshift-math.mjs';

const $ = id => document.getElementById(id);
const colors = ['#8dc9f1', '#91dfcb', '#d6d991', '#efbb84', '#e396ad', '#b4a1e2'];
let summary, current, epochs = [], arrays = [], index = 0, timer, version = 0;
let preparedSource, preparedBackground, preparedFrames;
const option = (value, text) => { const o = document.createElement('option'); o.value = value; o.textContent = text; return o; };
const fmt = (v, n = 2) => Number.isFinite(v) ? v.toLocaleString('en-US', { maximumFractionDigits: n }) : '—';
async function json(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}
function stop() { clearInterval(timer); timer = undefined; $('sky-play').textContent = '▶'; }
function draw() {
  if (!arrays.length) return;
  const background = $('sky-background').checked;
  if (preparedSource !== arrays || preparedBackground !== background) {
    preparedFrames = arrays.map(a => {
      if (!background) return a;
      const sky = median(a);
      return a.map(v => v - sky);
    });
    preparedSource = arrays; preparedBackground = background;
  }
  const processed = preparedFrames;
  let values = processed[index], lim = limits(processed, +$('sky-contrast').value);
  const mode = $('sky-mode').value;
  if (mode === 'mean') { values = mean(processed); lim = limits([values], +$('sky-contrast').value); }
  if (mode === 'difference') {
    values = difference(values, processed[0]);
    const diffs = processed.map(a => difference(a, processed[0]));
    lim = limits(diffs, +$('sky-contrast').value);
  }
  const [w, h] = current.frames.size;
  const small = document.createElement('canvas'); small.width = w; small.height = h;
  const sc = small.getContext('2d'), image = sc.createImageData(w, h);
  image.data.set(rgba(values, lim, mode === 'difference')); sc.putImageData(image, 0, 0);
  const c = $('sky-image'), ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#24313f'; ctx.fillRect(0, 0, c.width, c.height);
  ctx.strokeStyle = '#52616f';
  for (let x = -c.height; x < c.width; x += 12) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + c.height, c.height); ctx.stroke(); }
  const scale = Math.min((c.width - 30) / w, (c.height - 30) / h);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(small, (c.width - w * scale) / 2, (c.height - h * scale) / 2, w * scale, h * scale);
  const epoch = epochs[index];
  if ($('sky-overlays').checked && mode === 'blink') {
    const center = epoch.center || current.frames.center;
    const measured = current.frames.measured?.detections || [];
    const marks = [...measured.filter(d => d.epoch_id === epoch.id).map(d => ({ ...d, predicted: false })),
      ...(current.frames.known || []).filter(d => d.epoch_id === epoch.id).map(d => ({ ...d, predicted: true }))];
    for (const m of marks) {
      const p = project(m.ra, m.dec, center, [w, h], current.frames.pixel_arcsec);
      if (!p || !Number.isFinite(values[Math.round(p.y) * w + Math.round(p.x)])) continue;
      const x = (c.width - w * scale) / 2 + (p.x + .5) * scale;
      const y = (c.height - h * scale) / 2 + (p.y + .5) * scale;
      ctx.strokeStyle = m.predicted ? '#bd8708' : '#168da5'; ctx.lineWidth = 1.3;
      ctx.setLineDash(m.class === 'stack' ? [3, 3] : []);
      ctx.beginPath();
      if (m.predicted) { ctx.moveTo(x, y - 6); ctx.lineTo(x + 6, y); ctx.lineTo(x, y + 6); ctx.lineTo(x - 6, y); ctx.closePath(); }
      else ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.stroke(); ctx.setLineDash([]);
    }
  }
  $('sky-epoch').textContent = `${index + 1}/${epochs.length} · MJD ${fmt(epoch.mjd_mid, 6)}`;
  $('sky-time').value = index;
  $('sky-image-note').textContent = `${current.entry.name} · ${current.frames.clock} · D${epoch.det} · ${fmt(epoch.um_min, 4)}–${fmt(epoch.um_max, 4)} μm · ${epoch.n_exposures} exposure(s) · ${fmt(current.frames.pixel_arcsec, 3)}″/px · north ↑ / east ← · MJy/sr${mode === 'difference' ? ' (difference)' : ''}. ${background ? 'Median removed only in display.' : 'Original level of the derived product.'}`;
}
function spectrum() {
  const c = $('sky-spectrum'), ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  const all = current.object.spectrum;
  const points = all.filter(p => !p.saturated && Number.isFinite(p.flux_ujy) && p.err_ujy > 0 && Number.isFinite(p.err_ujy));
  $('sky-spectrum-note').textContent = `${points.length} sample(s) from 0.75–5.00 μm with uncertainty; ${all.filter(p => p.saturated).length} saturated sample(s) excluded. Colors indicate D1–D6; bars: ±1σ. Different epochs, without interpolation or replacing our photometry.`;
  ctx.fillStyle = '#9baeba'; ctx.font = '12px system-ui';
  if (!points.length) { ctx.fillText('No valid infrared samples in this product.', 30, 40); return; }
  const low = Math.min(...points.map(p => p.flux_ujy - p.err_ujy));
  const high = Math.max(...points.map(p => p.flux_ujy + p.err_ujy));
  const span = Math.max(high - low, 1), y0 = low - span * .05, y1 = high + span * .05;
  const x = um => 80 + (um - .75) / 4.25 * (c.width - 110);
  const y = f => 25 + (y1 - f) / (y1 - y0) * (c.height - 75);
  ctx.strokeStyle = '#52616f'; ctx.beginPath(); ctx.moveTo(80, 20); ctx.lineTo(80, c.height - 50); ctx.lineTo(c.width - 30, c.height - 50); ctx.stroke();
  for (let i = 0; i <= 4; i++) {
    const f = y0 + (y1 - y0) * i / 4; ctx.fillText(fmt(f, 1), 5, y(f));
    const um = .75 + 4.25 * i / 4; ctx.fillText(fmt(um), x(um) - 10, c.height - 30);
  }
  ctx.fillText('Published flux · μJy', 80, 15); ctx.fillText('Wavelength · μm', 330, c.height - 7);
  for (const p of points) {
    ctx.strokeStyle = ctx.fillStyle = colors[p.det - 1];
    ctx.beginPath(); ctx.moveTo(x(p.um), y(p.flux_ujy - p.err_ujy)); ctx.lineTo(x(p.um), y(p.flux_ujy + p.err_ujy)); ctx.stroke();
    ctx.beginPath(); ctx.arc(x(p.um), y(p.flux_ujy), 2, 0, Math.PI * 2); ctx.fill();
  }
}
function motion() {
  const m = current.object.measure;
  $('sky-motion').textContent = m
    ? `Published motion: ${fmt(m.shift_arcsec, 3)}″ ± ${fmt(m.sigma_arcsec, 3)}″ over ${fmt(m.dt_yr, 4)} year(s); prediction ${fmt(m.predicted_arcsec, 3)}″. ${m.source ? `D${m.source.det}, visits ${m.source.visits.join(' and ')}.` : 'Measurement detector/visits are not specified in this product.'} Reference-object measurement, independent of the displayed frame and our analysis.`
    : `No published displacement measurement for this object. ${current.object.measure_reason || ''}`;
}
async function selectDetector() {
  stop(); const request = ++version;
  arrays = []; $('sky-play').disabled = true;
  $('sky-image').getContext('2d').clearRect(0, 0, 800, 600);
  $('sky-image-note').textContent = 'Loading frames for the selected detector…';
  const det = +$('sky-detector').value;
  epochs = current.frames.epochs.filter(e => e.det === det).sort((a, b) => a.mjd_mid - b.mjd_mid);
  $('sky-status').textContent = `Loading ${epochs.length} frame(s) from D${det}…`;
  try {
    const result = [];
    // Keep acquisition bounded, and discard stale responses after a selection change.
    for (const e of epochs) {
      const res = await fetch(e.data_url);
      if (!res.ok) throw new Error(`Image unavailable: HTTP ${res.status}`);
      const bytes = await res.arrayBuffer();
      if (request !== version) return;
      result.push(decode(bytes, e, current.frames.size));
    }
    arrays = result; index = 0; $('sky-time').max = Math.max(0, epochs.length - 1);
    const aligned = sameGrid(epochs, current.frames.center);
    for (const o of $('sky-mode').options) o.disabled = o.value !== 'blink' && !aligned;
    $('sky-mode').value = 'blink';
    $('sky-play').disabled = arrays.length < 2;
    $('sky-status').textContent = `${summary.summary.candidates.toLocaleString('en-US')} candidates in the public archive; ${summary.objects.length} objects with detailed products. Source ${summary.commit.slice(0, 7)}. ${aligned ? 'Shared grid in this set.' : 'Varying centers: mean/difference unavailable.'}`;
    draw();
  } catch (e) { if (request === version) $('sky-status').textContent = e.message; }
}
async function selectSet() {
  stop(); const request = ++version; arrays = [];
  $('sky-image').getContext('2d').clearRect(0, 0, 800, 600);
  try {
    const result = await json(`/api/skyshift/object?slug=${encodeURIComponent($('sky-object').value)}&frames=${encodeURIComponent($('sky-set').value)}`);
    if (request !== version) return;
    current = result;
    const dets = [...new Set(current.frames.epochs.map(e => e.det))].sort();
    $('sky-detector').replaceChildren(...dets.map(d => option(d, `D${d}`)));
    $('sky-detector').value = String(dets[0]);
    spectrum(); motion(); await selectDetector();
  } catch (e) { if (request === version) $('sky-status').textContent = e.message; }
}
async function selectObject() {
  stop(); const request = ++version; arrays = []; epochs = [];
  const obj = summary.objects.find(o => o.slug === $('sky-object').value);
  if (!obj.sets.length) {
    const result = await json(`/api/skyshift/object?slug=${encodeURIComponent(obj.slug)}`);
    if (request !== version) return;
    current = result;
    $('sky-set').replaceChildren(option('', 'No precomputed images'));
    $('sky-detector').replaceChildren(); $('sky-play').disabled = true;
    $('sky-image').getContext('2d').clearRect(0, 0, 800, 600);
    $('sky-image-note').textContent = 'This object has a spectral product but no precomputed public images.';
    $('sky-epoch').textContent = ''; $('sky-status').textContent = 'Spectral product loaded; image unavailable.';
    spectrum(); motion(); return;
  }
  $('sky-set').replaceChildren(...obj.sets.map(s => option(s.file, `${s.clock === 'months' ? 'Visits' : 'Exposures'}${s.fov ? ` · ${s.fov}′` : ''}`)));
  $('sky-set').value = obj.sets[0].file;
  await selectSet();
}
$('sky-object').addEventListener('change', selectObject);
$('sky-set').addEventListener('change', selectSet);
$('sky-detector').addEventListener('change', selectDetector);
for (const id of ['sky-mode', 'sky-background', 'sky-contrast', 'sky-overlays']) $(id).addEventListener('input', draw);
$('sky-time').addEventListener('input', () => { stop(); index = +$('sky-time').value; draw(); });
$('sky-play').addEventListener('click', () => {
  if (timer) return stop();
  if (arrays.length < 2) return;
  $('sky-play').textContent = 'Ⅱ';
  timer = setInterval(() => { index = (index + 1) % arrays.length; draw(); }, 650);
});
document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
try {
  summary = await json('/api/skyshift');
  $('sky-loaded').hidden = false;
  $('sky-object').replaceChildren(...summary.objects.map(o => option(o.slug, o.name)));
  $('sky-object').value = summary.objects.find(o => o.slug === 'barnard')?.slug || summary.objects[0]?.slug;
  const analysis = summary.analysis;
  const reasons = {
    'A agregação usa medidas publicadas; recuperação/astrometria bruta requer novos recortes.': 'Aggregation uses published measurements; raw retrieval/astrometry requires new cutouts.',
    'Tabelas Parquet das zonas e órfãos não constam em web/public/data.': 'Zone and orphan Parquet tables are not included in web/public/data.',
    'Ajustes físicos completos requerem recortes e geometria Horizons; não foram inferidos do RGB.': 'Full physical fits require cutouts and Horizons geometry; they were not inferred from RGB.',
    'Produtos públicos foram importados; não houve novo levantamento nem teste de latência remoto.': 'Public products were imported; no new survey or remote latency test was performed.',
  };
  const names = { build_validation: 'Validations', distant: 'Distant objects', native_photometry: 'Independent photometry' };
  $('sky-analysis').textContent = analysis ? [
    ...(analysis.runs || []).map(r => `${names[r.name] || 'Analysis'}: ${r.status}`),
    ...(analysis.checks || []).map(c => `${c.id} · ${c.status}: ${c.headline}`),
    ...(analysis.not_rerun || []).map(r => `Not recalculated: ${reasons[r.reason] || r.reason}`),
  ].join('\n\n') : 'Analyses have not been run yet.';
  await selectObject();
} catch (e) { $('sky-status').textContent = e.message; }
