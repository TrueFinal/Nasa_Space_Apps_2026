import { cropFor, available, starsFor, segmentsFor, backgroundFor, limitsFor, stretch, viewport, imagePoint, pixelAt, spectralPoints } from './plate.mjs';
const $ = id => document.getElementById(id);
let report, allFrames = [], index = 0, mode = 'science', timer, imageView, gaiaAvailable = false;
let joinedSamples = [], channelData = [], playbackWanted = false, stackURL;
const bandColors = ['#8dc9f1', '#91dfcb', '#d6d991', '#efbb84', '#e396ad', '#b4a1e2'];
const nominalBands = [[.75, 1.09], [1.10, 1.62], [1.63, 2.41], [2.42, 3.82], [3.83, 4.41], [4.42, 5.00]];
const statuses = { aperture_measurement: 'Aperture measured', masked_aperture: 'Masked aperture', insufficient_background: 'Insufficient background', target_outside_image: 'Target outside image', aperture_or_background_at_edge: 'Aperture at image edge' };
const number = (v, digits = 2) => v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('en-US', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const node = (tag, text, className) => { const el = document.createElement(tag); el.textContent = text; if (className) el.className = className; return el; };
function translate(text) {
  const phrases = {
    'Iniciando consulta':'Starting query', 'Consultando posições e exposições no MOST/IRSA':'Querying positions and exposures in MOST/IRSA', 'Consultando Gaia DR3 para sinalizar contaminação':'Querying Gaia DR3 for nearby stellar sources', 'Gerando plotagem com cobertura válida':'Rendering valid image coverage', 'Análise concluída':'Analysis complete', 'Baixando calibração oficial':'Downloading official calibration', 'Inspecionando recorte':'Inspecting cutout', 'Processando exposição':'Processing exposure',
    'Parâmetro de consulta desconhecido.':'Unknown query parameter.', 'Identificação MPC inválida.':'Invalid MPC designation.', 'O piloto aceita intervalos maiores que zero e de até sete dias.':'Choose an interval longer than zero and no longer than seven days.', 'Número de exposições deve ser inteiro.':'Exposure count must be an integer.', 'Detector deve ser inteiro.':'Detector must be an integer.', 'Já existe uma consulta em processamento.':'A query is already running.', 'Calibrações ausentes:':'Missing calibrations:', 'Execute calibration --detector all e reinicie com a pasta de calibrações.':'Run calibration --detector all and restart with the calibration directory.', 'MOST não retornou tabela de exposições. Verifique objeto e datas.':'MOST returned no exposure table. Check the object and dates.', 'Nenhuma exposição coloca o alvo na faixa calibrada. Altere datas/alvo; não foi substituída por outra banda.':'No exposure places the target within the calibrated band. Change the dates or target; no alternative band was substituted.', 'Nenhuma análise carregada':'No analysis loaded', 'Origem não autorizada':'Unauthorized origin', 'Arquivo não encontrado':'File not found', 'Rota não encontrada':'Route not found',
    'MPC fornece órbitas/identificações; as imagens são do arquivo SPHEREx/IRSA.':'MPC supplies orbits and identifiers; images come from the SPHEREx/IRSA archive.',
    'Janela seleciona o centro CWAVE do pixel; CBAND é a largura efetiva do instrumento.':'The range selects pixel CWAVE centers; CBAND is the effective instrument bandwidth.',
    'Fluxo de abertura sem correção de PSF; erros condicionais a pixels independentes, sem erro sistemático de calibração/ZODI/astrometria.':'Aperture flux without PSF correction; errors assume independent pixels and exclude calibration, ZODI and astrometric systematics.',
    'Posições MOST exigem validação do observador; medidas na posição prevista não confirmam uma detecção.':'MOST positions require observer validation; measurements at predicted positions do not confirm detections.',
    'Gaia não é um catálogo infravermelho completo; ausência de associação não prova ausência de contaminação.':'Gaia is not a complete infrared catalog; no association does not prove the absence of contamination.',
    'As imagens no painel usam pixels nativos; cada exposição tem seu próprio WCS, sem reamostragem para fotometria.':'Images use native pixels and each exposure has its own WCS; photometry does not use resampled pixels.',
    'WISE W1 é uma banda larga e não equivale a esta janela SPHEREx; não há subtração WISE/SPHEREx.':'WISE W1 is a broad band and is not equivalent to this SPHEREx range; WISE is not subtracted from SPHEREx.',
    'Detectores e centros de banda diferentes não constituem uma curva de luz em banda fixa. O espectro é amostrado em épocas distintas, sem interpolação em lacunas.':'Different detectors and band centers do not form a fixed-band light curve. The spectrum samples different epochs without interpolation across gaps.'
  };
  let result=String(text);
  for(const [original,english] of Object.entries(phrases)) result=result.replaceAll(original,english);
  return result;
}
function status(text, error = false) { $('status').textContent = translate(text); $('status').className = error ? 'error' : ''; }
async function api(path, options) { const res = await fetch(path, options); const data = await res.json(); if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`); return data; }
function stop() { playbackWanted = false; clearInterval(timer); timer = undefined; $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Play exposures'); $('by-frame').setAttribute('aria-pressed', 'true'); }
async function load() {
  report = await api('/api/report'); index = 0; stop();
  const excluded = report.frames.filter(f => f.plot?.eligible === false);
  allFrames = report.frames.filter(f => f.plot?.eligible !== false).sort((a, b) => a.mjd_utc - b.mjd_utc);
  report.frames = allFrames;
  if (!report.frames.length) {
    $('empty').hidden = false; $('loaded').hidden = true;
    status('No image has valid coverage at the selected MPC/MOST position and wavelength range. Points without coverage were not plotted.', true);
    return false;
  }
  $('empty').hidden = true; $('loaded').hidden = false; $('synthetic').hidden = !report.synthetic;
  $('dataset').textContent = report.synthetic ? 'SYNTHETIC DATA · VALIDATION' : 'REAL EXPOSURES · SPHEREx / IRSA';
  $('object').textContent = report.synthetic ? 'Synthetic demonstration — not NASA observations' : report.object; $('band').textContent = `${number(report.config.low_um)}–${number(report.config.high_um)} μm`;
  for (const key of ['low_um', 'high_um', 'max_exposures', 'detector']) {
    if ($('query').elements[key]) $('query').elements[key].value = report.config[key] ?? 0;
  }
  const options = [node('option', 'All observed detectors')]; options[0].value = '0';
  for (const d of [...new Set(allFrames.map(f => f.detector).filter(Boolean))].sort()) {
    const option = node('option', `D${d} · ${allFrames.filter(f => f.detector === d).length} image(s)`);
    option.value = String(d); options.push(option);
  }
  $('detector-view').replaceChildren(...options); $('detector-view').value = '0';
  $('band-coverage').replaceChildren(...nominalBands.map(([lo, hi], i) => {
    const d = i + 1, entry = report.spectral_coverage?.find(c => c.detector === d);
    const frames = allFrames.filter(f => f.detector === d), measured = frames.filter(f => f.measurement.flux_ujy != null).length;
    const card = node('div', '', 'band-tile'); card.dataset.detector = String(d);
    const label = entry?.status === 'not_requested' ? 'Not requested' : !entry?.exposures && !frames.length ? 'Not observed' : `${frames.length} image(s) · ${measured} measurement(s)`;
    card.append(node('strong', `D${d}`), node('span', `${number(lo)}–${number(hi)} μm`), node('small', label));
    return card;
  }));
  $('time').max = report.frames.length - 1; $('time').value = 0;
  $('limitations').replaceChildren(...report.limitations.map(s => node('li', translate(s))));
  $('provenance').textContent = JSON.stringify(report.provenance, null, 2);
  joinedSamples = report.dataset_join?.samples || [];
  const sampleSelect = $('sample-select');
  if (sampleSelect) {
    const first = node('option', 'Moving object position · MOST'); first.value = '';
    sampleSelect.replaceChildren(first, ...joinedSamples.map(s => {
      const option = node('option', `${s.kind === 'target' ? 'Target' : 'Gaia'} · C${s.channel_id ?? '?'} · ${number(s.ra, 5)}, ${number(s.dec, 5)} · ${s.utc}`);
      option.value = s.id; return option;
    }));
  }
  $('joined-panel').hidden = !report.dataset_join;
  if (report.dataset_join) $('joined-summary').textContent = `${joinedSamples.length} candidate positions across ${report.dataset_join.channels.filter(c => c.samples > 0).length}/102 SPHEREx channels. Positional matches are candidates, not confirmed identities.`;
  const gaia = typeof report.gaia_status === 'object' ? report.gaia_status.status : report.gaia_status;
  gaiaAvailable = ['loaded', 'provided', 'synthetic', 'incomplete'].includes(gaia);
  $('gaia-overlay').disabled = !gaiaAvailable;
  $('gaia-overlay').checked = gaiaAvailable;
  $('gaia-notice').hidden = gaiaAvailable && gaia !== 'incomplete';
  $('gaia-notice').textContent = gaiaAvailable
    ? 'Partial Gaia coverage: only compatible records available for this image are displayed.'
    : 'Gaia is unavailable or was not supplied: no Gaia sources were plotted. The SPHEREx image is still available; the stellar mask is incomplete.';
  $('excluded-note').textContent = excluded.length ? `${excluded.length} exposure(s) excluded from the plot because the MPC/MOST position has no coverage. See the JSON for details.` : '';
  if (report.plotting?.preview) { $('preview').hidden = false; $('preview').href = `/${report.plotting.preview}`; }
  else $('preview').hidden = true;
  $('gif-download').hidden = false;
  $('gif-download').href = '/files/animation.gif?palette=gray_r&' + Date.now();
  setupStack();
  render();
  startPlayback();
  return true;
}
function drawImage() {
  if (!report?.frames.length) return;
  const f = report.frames[index], array = f[mode], scope = $('scope').value || 'target';
  const crop = cropFor(f, scope), { w: width, h: height } = crop;
  const canvas = $('image'), ctx = canvas.getContext('2d');
  imageView = viewport(crop, canvas.width, canvas.height);
  const small = document.createElement('canvas'); small.width = width; small.height = height;
  const sc = small.getContext('2d'), pixels = sc.createImageData(width, height);
  const photometric = !['mask', 'wavelength'].includes(mode);
  const limits = photometric ? limitsFor(allFrames, mode, scope, Number($('contrast').value || .3), f.detector) : null;
  const background = photometric ? backgroundFor(f, mode, scope) : 0;
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    const nx = x + crop.x, ny = y + crop.y;
    const value = array[ny][nx], bits = f.mask[ny][nx]; let rgb;
    if (mode === 'mask') rgb = bits & 1 || bits & 2 ? [224, 74, 88] : bits & 16 ? [90, 88, 105] : bits & 4 ? [69, 45, 100] : bits & 8 ? [223, 178, 72] : bits & 32 ? [33, 137, 156] : [10, 24, 35];
    else if (value == null || !available(f, { x: nx, y: ny }, crop)) rgb = (x + y) % 4 < 2 ? [195, 195, 195] : [225, 225, 225];
    else {
      if (mode === 'wavelength') {
        const t = Math.max(0, Math.min(1, (value - report.config.low_um) / (report.config.high_um - report.config.low_um)));
        rgb = [60 + 170 * t, 145 - 80 * t, 225 - 160 * t];
      } else { const v = Math.round(255 * (1 - stretch(value - background, limits))); rgb = [v, v, v]; }
    }
    // FITS y=0 is the bottom row; display the sky with y increasing upwards.
    const p = ((height - 1 - y) * width + x) * 4;
    pixels.data.set([...rgb, 255], p);
  }
  sc.putImageData(pixels, 0, 0); ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#080e15'; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(small, imageView.left, imageView.top, imageView.width, imageView.height);
  ctx.strokeStyle = '#405564'; ctx.lineWidth = 1;
  ctx.strokeRect(imageView.left, imageView.top, imageView.width, imageView.height);
  ctx.font = '11px system-ui'; ctx.fillStyle = '#9baeba';
  for (let i = 0; i <= 4; i++) {
    const x = Math.round(crop.x + (crop.w - 1) * i / 4), y = Math.round(crop.y + (crop.h - 1) * i / 4);
    const [px] = imagePoint({ x, y: crop.y }, imageView), [, py] = imagePoint({ x: crop.x, y }, imageView);
    ctx.fillText(String(x), px - 7, imageView.top + imageView.height + 17);
    ctx.fillText(String(y), imageView.left - 28, py + 3);
  }
  ctx.fillText('Native X · pixel', imageView.left + imageView.width / 2 - 40, imageView.top + imageView.height + 36);
  ctx.fillText('Y', imageView.left - 28, imageView.top - 8);
  const bandOnly = mode === 'masked' || mode === 'wavelength';
  const stars = starsFor(f, scope, bandOnly, gaiaAvailable && $('gaia-overlay').checked);
  ctx.save(); ctx.beginPath(); ctx.rect(imageView.left, imageView.top, imageView.width, imageView.height); ctx.clip();
  if ($('overlays').checked) {
    ctx.strokeStyle = '#72d9ee'; ctx.lineWidth = 1.2; ctx.setLineDash([5, 4]);
    for (const segment of segmentsFor(f, scope, bandOnly)) {
      ctx.beginPath(); segment.forEach((p, i) => { const [x, y] = imagePoint(p, imageView); if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y); }); ctx.stroke();
    }
    ctx.setLineDash([]);
    if (available(f, f.target, crop, bandOnly)) {
      const [tx, ty] = imagePoint(f.target, imageView);
      ctx.beginPath(); ctx.arc(tx, ty, report.config.aperture_px * imageView.scale, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(tx - 4, ty); ctx.lineTo(tx + 4, ty); ctx.moveTo(tx, ty - 4); ctx.lineTo(tx, ty + 4); ctx.stroke();
    }
  }
  ctx.strokeStyle = '#f4ce75'; ctx.lineWidth = 1;
  for (const star of stars) { const [x, y] = imagePoint(star, imageView); ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.stroke(); }
  const compass = f.plot?.compass || {};
  const cx = imageView.left + imageView.width - 45, cy = imageView.top + 48;
  ctx.fillStyle = '#b4c9d5'; ctx.strokeStyle = '#b4c9d5';
  for (const [label, direction] of Object.entries(compass)) {
    ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx + 25 * direction.x, cy - 25 * direction.y); ctx.stroke();
    ctx.fillText(label, cx + 33 * direction.x - 3, cy - 33 * direction.y + 3);
  }
  ctx.restore();
  const arcsec = f.plot?.pixel_arcsec;
  $('field-label').textContent = `${crop.w} × ${crop.h} px${arcsec ? ` · ≈ ${number(crop.w * arcsec / 60, 1)}′` : ''} · ${scope === 'target' ? 'cutout at MPC/MOST prediction' : 'available FITS field'}`;
  $('plot-note').textContent = `Gaia: ${gaiaAvailable ? `${stars.length} compatible source(s) in this view` : 'unavailable; no overlay points'}. ${f.plot?.counts?.excluded_from_image ?? 0} record(s) outside coverage excluded. Hatched areas contain no accepted data.`;
  $('stretch-note').textContent = limits ? `White → black · logarithmic stretch · shared scale within detector D${f.detector ?? 4} · background removed for display only · ${number(limits.lo, 4)} to ${number(limits.hi, 4)} MJy/sr.` : mode === 'mask' ? 'Colors indicate exclusion reasons and review flags.' : `CWAVE band centers · ${number(report.config.low_um)}–${number(report.config.high_um)} μm.`;
}
function plot() {
  const c = $('photometry'), ctx = c.getContext('2d'); ctx.clearRect(0, 0, c.width, c.height);
  const axis = $('plot-axis').value === 'time' ? 'time' : 'spectrum';
  const points = spectralPoints(report.frames, axis);
  ctx.font = '13px system-ui'; ctx.fillStyle = '#9baeba';
  if (!points.length) { ctx.fillText('No valid apertures for flux measurement in this selection.', 20, 100); return; }
  const min = Math.min(0, ...points.map(p => p.flux_ujy - p.error_ujy));
  const max = Math.max(...points.map(p => p.flux_ujy + p.error_ujy));
  let xlo = axis === 'spectrum' ? report.config.low_um : Math.min(...points.map(p => p.x));
  let xhi = axis === 'spectrum' ? report.config.high_um : Math.max(...points.map(p => p.x));
  if (xhi === xlo) { xlo -= 60000; xhi += 60000; }
  const x = value => 80 + (value - xlo) * 740 / (xhi - xlo);
  const y = value => 235 - (value - min) / Math.max(1e-12, max - min) * 195;
  ctx.strokeStyle = '#324555'; ctx.beginPath(); ctx.moveTo(80, 25); ctx.lineTo(80, 240); ctx.lineTo(840, 240); ctx.stroke();
  ctx.fillText(`${number(max, 1)} μJy`, 2, 35); ctx.fillText(number(min, 1), 4, 237);
  for (let i = 0; i <= 4; i++) {
    const value = xlo + (xhi - xlo) * i / 4;
    const label = axis === 'spectrum' ? `${number(value)} μm` : new Date(value).toISOString().slice(11, 19);
    ctx.fillText(label, x(value) - 24, 264);
  }
  for (const p of points) {
    const px = x(p.x), py = y(p.flux_ujy); ctx.strokeStyle = ctx.fillStyle = bandColors[(p.detector ?? 4) - 1];
    const low = y(p.flux_ujy - p.error_ujy), high = y(p.flux_ujy + p.error_ujy);
    ctx.beginPath(); ctx.moveTo(px, low); ctx.lineTo(px, high);
    ctx.moveTo(px - 4, low); ctx.lineTo(px + 4, low); ctx.moveTo(px - 4, high); ctx.lineTo(px + 4, high);
    if (axis === 'spectrum' && Number.isFinite(p.bandwidth_um)) {
      ctx.moveTo(x(Math.max(xlo, p.x - p.bandwidth_um / 2)), py);
      ctx.lineTo(x(Math.min(xhi, p.x + p.bandwidth_um / 2)), py);
    }
    ctx.stroke(); ctx.beginPath(); ctx.arc(px, py, p.i === index ? 6 : 4, 0, 2 * Math.PI); ctx.fill();
  }
  ctx.fillStyle = '#9baeba'; ctx.fillText(axis === 'spectrum' ? 'λ CWAVE · error bars: CBAND and ±1σ' : `UTC · ${new Date(xlo).toISOString().slice(0, 10)} to ${new Date(xhi).toISOString().slice(0, 10)}`, 80, 292);
}
function render() {
  if (!report?.frames.length) return; const f = report.frames[index], m = f.measurement;
  const single = report.frames.length < 2;
  for (const id of ['play', 'previous-frame', 'next-frame']) $(id).disabled = single;
  $('playback-note').textContent = single ? 'Only one exposure is available in this selection. Expand the dates or exposure limit to animate or stack multiple frames.' : report.frames.length + ' exposures available for playback.';
  $('frame-band').textContent = `D${f.detector ?? 4} · ${number(f.central_wavelength_um ?? m.lambda_um, 4)} μm`;
  $('frame-label').textContent = `${index + 1} / ${report.frames.length}`; $('time').value = index;
  $('epoch').textContent = `${f.utc} UTC · ${f.source} · native pixels / exposure WCS`;
  $('fits').href = `/${f.fits}`;
  $('metrics').replaceChildren(...[[`${number(f.accepted_fraction * 100, 1)}%`, 'accepted pixels in cutout'], [`${number(m.coverage * 100, 1)}%`, 'aperture coverage'], [number(m.flux_ujy, 1), 'μJy in predicted aperture']].map(([value, label]) => { const card = node('div', '', 'metric'); card.append(node('strong', value), node('span', label)); return card; }));
  $('measurements').replaceChildren(...report.frames.map((frame, i) => {
    const a = frame.measurement, tr = node('tr', '', i === index ? 'selected' : ''); tr.tabIndex = 0;
    [`D${frame.detector ?? 4}`, frame.utc, number(a.lambda_um, 4), number(a.bandwidth_um, 4), a.flux_ujy == null ? '—' : `${number(a.flux_ujy)} ± ${number(a.error_ujy)}`, number(a.snr), `${number(100 * a.coverage, 1)}%`, statuses[a.status] || a.status].forEach(s => tr.append(node('td', s)));
    const select = () => { stop(); index = i; render(); }; tr.addEventListener('click', select); tr.addEventListener('keydown', e => { if (e.key === 'Enter') select(); }); return tr;
  }));
  const entries = { 'Target RA / Dec': `${number(f.target.ra, 7)}° / ${number(f.target.dec, 7)}°`, 'Position source': f.target.provider || 'Provided manifest', 'Astrometry': f.target.position_status || 'Unverified', 'Mask': statuses[m.status] || m.status, 'ZODI subtracted': f.zodi_subtracted ? 'Yes; FITS model' : 'No', 'Review flags': `${number(100 * f.advisory_fraction, 2)}% of pixels; retained`, 'Calibration': f.calibration.source, 'SHA-256 original': f.input_sha256, 'Output SHA-256': f.output_sha256 };
  $('metadata').replaceChildren(...Object.entries(entries).flatMap(([k, v]) => [node('dt', k), node('dd', v)]));
  drawImage(); plot();
}
$('time').addEventListener('input', e => { stop(); index = +e.target.value; render(); });
function startPlayback() {
  if (!report || report.frames.length < 2) return;
  stop(); playbackWanted = true;
  if (document.hidden) return;
  $('by-frame').setAttribute('aria-pressed', 'false');
  $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pause exposures');
  timer = setInterval(() => { index = (index + 1) % report.frames.length; render(); }, 1000);
}
$('play').addEventListener('click', () => timer ? stop() : startPlayback());
$('by-frame').addEventListener('click', () => { stop(); $('time').focus(); });
for (const [id, step] of [['previous-frame', -1], ['next-frame', 1]]) $(id).addEventListener('click', () => {
  if (!report?.frames.length) return; stop();
  index = (index + step + report.frames.length) % report.frames.length; render();
});
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { clearInterval(timer); timer = undefined; }
  else if (playbackWanted) startPlayback();
});
$('tabs').addEventListener('click', e => { if (!e.target.dataset.mode) return; mode = e.target.dataset.mode; for (const b of $('tabs').children) b.setAttribute('aria-pressed', String(b === e.target)); drawImage(); });
$('overlays').addEventListener('change', drawImage);
$('gaia-overlay').addEventListener('change', drawImage);
$('scope').addEventListener('change', drawImage);
$('contrast').addEventListener('input', drawImage);
$('plot-axis').addEventListener('change', plot);
$('detector-view').addEventListener('change', e => {
  if (!report) return;
  const detector = Number(e.target.value); stop(); index = 0;
  report.frames = allFrames.filter(f => !detector || f.detector === detector);
  $('time').max = Math.max(0, report.frames.length - 1); render();
});
$('full-spectrum').addEventListener('click', () => {
  const form = $('query').elements;
  form.low_um.value = .75; form.high_um.value = 5; form.detector.value = 0;
});
$('image').addEventListener('mousemove', e => {
  if (!report || !imageView) return; const f = report.frames[index], r = e.currentTarget.getBoundingClientRect();
  const p = pixelAt((e.clientX - r.left) / r.width * e.currentTarget.width, (e.clientY - r.top) / r.height * e.currentTarget.height, imageView);
  if (!p) { $('pixel').textContent = 'Outside the image area · no measurement here.'; return; }
  const { x, y } = p;
  const bits = f.mask[y][x], reasons = Object.entries(report.mask_bits).filter(([, bit]) => bits & bit).map(([name]) => name);
  $('pixel').textContent = `x ${x} · y ${y} · λ ${number(f.wavelength[y][x], 5)} μm · ${number(f.science[y][x], 4)} MJy/sr · ${reasons.join(', ') || 'accepted'}`;
});
$('query').addEventListener('submit', async e => {
  e.preventDefault(); stop(); $('run').disabled = true;
  try {
    const params = Object.fromEntries(new FormData(e.currentTarget));
    for (const k of ['low_um', 'high_um', 'max_exposures', 'detector', 'channel_id']) params[k] = Number(params[k] || 0);
    params.include_context = $('include-context').checked;
    const { job } = await api('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params) });
    for (;;) { const state = await api(`/api/jobs/${job}`); status(state.message, state.status === 'error'); if (state.status === 'error') throw new Error(state.message); if (state.status === 'complete') break; await new Promise(resolve => setTimeout(resolve, 1500)); }
    if (await load()) status('Analysis complete. Check coverage, flags and astrometry before interpreting measurements.');
  } catch (err) { status(err.message, true); } finally { $('run').disabled = false; }
});
try {
  const grid = await api('/api/channels'); channelData = grid.channels || [];
  const all = node('option', 'All 102 channels · custom wavelength range'); all.value = '0';
  $('channel-id').replaceChildren(all, ...channelData.map(c => { const o = node('option', `${c.id} · D${c.detector}/${c.subchannel} · ${number(c.center_um, 4)} μm`); o.value = String(c.id); return o; }));
} catch (err) { $('mpc-status').textContent = `Channel list unavailable: ${err.message}`; }
$('mpc-search').addEventListener('click', async () => {
  $('mpc-search').disabled = true; $('mpc-status').textContent = 'Searching the official MPC service…';
  try {
    const result = await api(`/api/mpc?object=${encodeURIComponent($('query').elements.object.value.trim())}`);
    const items = result.items || [];
    $('mpc-results').replaceChildren(...items.map(item => { const o = node('option', `${item.identifier} · ${item.name || item.type || 'MPC object'}`); o.value = item.identifier; return o; }));
    $('mpc-status').textContent = result.status === 'resolved' ? 'MPC identity resolved. Images will be requested from SPHEREx/IRSA.' : result.status === 'ambiguous' ? 'Several matches found. Select the correct object.' : 'No MPC match found.';
    if (result.status === 'resolved' && items[0]) $('query').elements.object.value = items[0].identifier;
  } catch (err) { $('mpc-status').textContent = err.message; } finally { $('mpc-search').disabled = false; }
});
$('mpc-results').addEventListener('change', e => { if (e.target.value) $('query').elements.object.value = e.target.value; });
try {
  const state = await api('/api/state');
  $('server-note').textContent = state.archive_ready ? `Live archive queries enabled. Calibrations: ${(state.available_detectors || [4]).map(d => `D${d}`).join(', ')}.` : 'Live queries require local CWAVE/CBAND calibrations. Existing processed results remain available.';
  if (state.has_report) { if (await load()) status('Analysis loaded. Select an exposure or inspect the mask.'); }
  else status('Server ready. No analysis loaded.');
} catch (err) { status(`Could not connect to Python processing: ${err.message}`, true); }

function stackFrames() {
  return allFrames.filter(f => f.detector === Number($('stack-detector').value));
}
function setupStack() {
  $('stack-result').hidden = true;
  $('stack-detector').replaceChildren(...[...new Set(allFrames.map(f => f.detector))].sort().map(d => {
    const o = node('option', 'D' + d + ' · ' + allFrames.filter(f => f.detector === d).length + ' frames');
    o.value = String(d); return o;
  }));
  const best = [...new Set(allFrames.map(f => f.detector))].sort((a,b) => allFrames.filter(f=>f.detector===b).length-allFrames.filter(f=>f.detector===a).length)[0];
  $('stack-detector').value = String(best); resetStackRange();
}
function resetStackRange() {
  const n = stackFrames().length;
  $('stack-start').value = 1; $('stack-start').max = n;
  $('stack-count').value = Math.min(5,n); $('stack-count').max = n;
  $('stack-result').hidden = true; updateStackRange();
}
function updateStackRange() {
  const frames = stackFrames(), start = Number($('stack-start').value)-1, count = Number($('stack-count').value);
  const valid = Number.isInteger(start) && Number.isInteger(count) && start>=0 && count>=2 && start+count<=frames.length;
  $('build-stack').disabled = !valid;
  $('stack-range').textContent = valid ? frames[start].utc + ' → ' + frames[start+count-1].utc + ' UTC · ' + count + ' frames' : 'Select at least 2 available frames within this detector.';
}
$('stack-detector').addEventListener('change', resetStackRange);
for (const id of ['stack-start','stack-count']) $(id).addEventListener('input', updateStackRange);
$('build-stack').addEventListener('click', async () => {
  $('build-stack').disabled = true; $('stack-status').textContent = 'Aligning sky positions and stacking…';
  try {
    const query = new URLSearchParams({detector:$('stack-detector').value, start:String(Number($('stack-start').value)-1), count:$('stack-count').value});
    const res = await fetch('/api/stack?' + query);
    if (!res.ok) { const error = await res.json(); throw new Error(error.error); }
    const blob = await res.blob();
    if (stackURL) URL.revokeObjectURL(stackURL);
    stackURL = URL.createObjectURL(blob); $('stack-image').src = stackURL;
    $('stack-download').href = stackURL; $('stack-result').hidden = false;
    $('stack-status').textContent = 'Sky-aligned maximum brightness: stationary stars overlap; moving sources may appear at several positions. Empty areas are hatched. A continuous trail needs overlapping sky coverage.';
  } catch (error) { $('stack-status').textContent = error.message; }
  finally { updateStackRange(); }
});
