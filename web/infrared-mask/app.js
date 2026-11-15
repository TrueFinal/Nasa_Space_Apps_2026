import { cropFor, available, starsFor, segmentsFor, backgroundFor, limitsFor, stretch, viewport, imagePoint, pixelAt, spectralPoints, plateRGB, playbackFrames } from './plate.mjs';
const $ = id => document.getElementById(id);
let report, allFrames = [], index = 0, mode = 'science', timer, imageView, gaiaAvailable = false;
let channelData = [], joinedSamples = [];
const bandColors = ['#8dc9f1', '#91dfcb', '#d6d991', '#efbb84', '#e396ad', '#b4a1e2'];
const nominalBands = [[.75, 1.09], [1.10, 1.62], [1.63, 2.41], [2.42, 3.82], [3.83, 4.41], [4.42, 5.00]];
const statuses = { aperture_measurement: 'Abertura medida', masked_aperture: 'Abertura mascarada', insufficient_background: 'Fundo insuficiente', target_outside_image: 'Alvo fora da imagem', aperture_or_background_at_edge: 'Abertura na borda' };
const number = (v, digits = 2) => v == null || !Number.isFinite(v) ? '—' : v.toLocaleString('pt-BR', { maximumFractionDigits: digits, minimumFractionDigits: digits });
const node = (tag, text, className) => { const el = document.createElement(tag); el.textContent = text; if (className) el.className = className; return el; };
function status(text, error = false) { $('status').textContent = text; $('status').className = error ? 'error' : ''; }
async function api(path, options) { const res = await fetch(path, options); const data = await res.json(); if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`); return data; }
function stop() { clearInterval(timer); timer = undefined; $('play').textContent = '▶'; $('play').setAttribute('aria-label', 'Reproduzir exposições'); }
function applyChannel() {
  const channel = channelData.find(c => c.id === Number($('channel-id').value));
  const form = $('query').elements;
  if (channel) {
    form.low_um.value = Math.max(.75, channel.low_um); form.high_um.value = Math.min(5, channel.high_um);
    form.detector.value = channel.detector;
    $('channel-info').textContent = `Canal ${channel.id} · D${channel.detector}/${channel.subchannel} · centro ${number(channel.center_um, 4)} μm. Limites oficiais aplicados à seleção CWAVE; não preenchem cobertura ausente.`;
  } else $('channel-info').textContent = 'Janela livre nos 102 canais. CWAVE/CBAND continuam definindo os pixels aceitos.';
}
function sampleInfo() {
  const sample = joinedSamples.find(s => s.id === $('sample-select').value);
  $('context-links').replaceChildren();
  if (!sample) { $('sample-info').textContent = 'Busca na trajetória MPC/MOST. Selecione uma amostra para buscar imagens em coordenadas fixas do céu.'; return; }
  $('sample-info').textContent = `ICRS ${number(sample.ra, 7)}°, ${number(sample.dec, 7)}° · ${sample.utc} UTC · canal ${sample.channel_id ?? 'não atribuído'}. Gaia: ${sample.gaia_candidates.length}; AllWISE: ${sample.allwise_candidates.length}; NEOWISE: ${sample.neowise_candidates.length} candidato(s). Posição fixa, sem previsão de movimento.`;
  for (const [title, url] of [['Abrir imagens no WISEView ↗', sample.wiseview_url], ...sample.wise_images.map(i => [`FITS AllWISE ${i.band} · contexto de outra época ↗`, i.url])]) {
    const link = node('a', title); link.href = url; link.target = '_blank'; link.rel = 'noopener'; $('context-links').append(link);
  }
}
function populateSamples() {
  joinedSamples = report?.dataset_join?.samples || [];
  const base = node('option', 'Trajetória do objeto MPC · MOST'); base.value = '';
  $('sample-select').replaceChildren(base, ...joinedSamples.map(s => {
    const option = node('option', `${s.kind === 'target' ? 'Previsão' : 'Gaia'} · C${s.channel_id ?? '?'} · ${number(s.ra, 5)}, ${number(s.dec, 5)} · ${s.utc}`);
    option.value = s.id; return option;
  }));
  $('sample-select').value = '';
  $('joined-panel').hidden = !report?.dataset_join;
  const joined = report?.dataset_join;
  if (joined) {
    const covered = joined.channels.filter(c => c.samples > 0).length;
    $('joined-summary').textContent = `${joinedSamples.length} amostra(s) em ${covered}/102 canais SPHEREx. Canais sem observação permanecem sem medida.`;
    const states = Object.entries(joined.catalogue_status).map(([key, value]) => `${key}: ${value.status}`);
    $('joined-status').textContent = states.length ? states.join(' · ') : 'AllWISE / NEOWISE não consultados nesta análise; nenhum registro externo foi inventado.';
  }
  sampleInfo();
}
async function load() {
  report = await api('/api/report'); index = 0; stop();
  populateSamples();
  const external = report.skyshift_context;
  $('sky-context-panel').hidden = !external;
  if (external) {
    const compatible = external.matches.filter(m => m.epoch_compatible).length;
    $('sky-context').textContent = `${external.samples_checked} amostra(s) verificadas · ${external.matches.length} associação(ões) posicionais · ${compatible} compatível(is) em época. Revisão ${external.commit.slice(0, 7)}. ${external.matches.length ? 'Revise separação, época e detector no JSON.' : 'Nenhum candidato dentro do raio; as medidas locais permanecem preservadas.'}`;
    if (report.skyshift_photometry) $('sky-context').textContent += ` Fotometria independente de referência: ${report.skyshift_photometry.accepted}/${report.skyshift_photometry.total} exposições aceitas, com recentragem e correção de abertura. Não aplica a nossa máscara Gaia; consulte a coluna adicional e a proveniência.`;
  }
  const excluded = report.frames.filter(f => f.plot?.eligible === false);
  allFrames = report.frames.filter(f => f.plot?.eligible !== false);
  report.frames = allFrames;
  if (!report.frames.length) {
    $('empty').hidden = false; $('loaded').hidden = true;
    status('Nenhuma imagem tem cobertura válida na posição MPC/MOST e faixa selecionada. Os pontos sem imagem não foram plotados.', true);
    return false;
  }
  $('empty').hidden = true; $('loaded').hidden = false; $('synthetic').hidden = !report.synthetic;
  $('dataset').textContent = report.synthetic ? 'DADOS SINTÉTICOS · VALIDAÇÃO' : 'EXPOSIÇÕES REAIS · SPHEREx / IRSA';
  $('object').textContent = report.object; $('band').textContent = `${number(report.config.low_um)}–${number(report.config.high_um)} μm`;
  for (const key of ['low_um', 'high_um', 'max_exposures', 'detector']) {
    if ($('query').elements[key]) $('query').elements[key].value = report.config[key] ?? 0;
  }
  const options = [node('option', 'Todos os detectores observados')]; options[0].value = '0';
  for (const d of [...new Set(allFrames.map(f => f.detector).filter(Boolean))].sort()) {
    const option = node('option', `D${d} · ${allFrames.filter(f => f.detector === d).length} imagem(ns)`);
    option.value = String(d); options.push(option);
  }
  $('detector-view').replaceChildren(...options); $('detector-view').value = '0';
  $('band-coverage').replaceChildren(...nominalBands.map(([lo, hi], i) => {
    const d = i + 1, entry = report.spectral_coverage?.find(c => c.detector === d);
    const frames = allFrames.filter(f => f.detector === d), measured = frames.filter(f => f.measurement.flux_ujy != null).length;
    const card = node('div', '', 'band-tile'); card.dataset.detector = String(d);
    const label = entry?.status === 'not_requested' ? 'Não solicitado' : !entry?.exposures && !frames.length ? 'Não observado' : `${frames.length} imagem(ns) · ${measured} medida(s)`;
    card.append(node('strong', `D${d}`), node('span', `${number(lo)}–${number(hi)} μm`), node('small', label));
    return card;
  }));
  $('time').max = report.frames.length - 1; $('time').value = 0;
  $('limitations').replaceChildren(...report.limitations.map(s => node('li', s)));
  $('provenance').textContent = JSON.stringify(report.provenance, null, 2);
  const gaia = typeof report.gaia_status === 'object' ? report.gaia_status.status : report.gaia_status;
  gaiaAvailable = ['loaded', 'provided', 'synthetic', 'incomplete'].includes(gaia);
  $('gaia-overlay').disabled = !gaiaAvailable;
  $('gaia-overlay').checked = gaiaAvailable;
  $('gaia-notice').hidden = gaiaAvailable && gaia !== 'incomplete';
  $('gaia-notice').textContent = gaiaAvailable
    ? 'Cobertura Gaia parcial: apenas registros disponíveis e compatíveis com a imagem são exibidos.'
    : 'Gaia indisponível ou não fornecido: nenhuma fonte Gaia foi plotada. A imagem SPHEREx continua disponível; a máscara estelar está incompleta.';
  $('excluded-note').textContent = excluded.length ? `${excluded.length} exposição(ões) excluída(s) da plotagem por falta de cobertura na posição MPC/MOST. Detalhes no JSON.` : '';
  if (report.plotting?.preview) { $('preview').hidden = false; $('preview').href = `/${report.plotting.preview}`; }
  else $('preview').hidden = true;
  const mosaic = report.color_mosaic;
  $('color-mosaic').hidden = !mosaic?.preview;
  if (mosaic?.preview) {
    // Version the URL because each new analysis reuses the output filenames.
    const version = encodeURIComponent(report.created_utc || '');
    $('color-preview').src = `/${mosaic.preview}?v=${version}`;
    $('color-download').href = `/${mosaic.preview}?v=${version}`;
    const coverage = mosaic.channels.map(c => `${c.channel}: ${number(100 * c.coverage_fraction, 1)}%`).join(' · ');
    const epochs = (mosaic.contributors || []).map(c => c.utc).sort();
    $('color-coverage').textContent = `Cobertura por canal: ${coverage}. RGB completo: ${number(100 * mosaic.complete_rgb_fraction, 1)}%. Campo: ${mosaic.shape[1]} × ${mosaic.shape[0]} px, referência ${mosaic.reference_frame || 'cubo IRSA'}.${epochs.length ? ` Épocas UTC: ${epochs[0]} a ${epochs.at(-1)}.` : ''}`;
  }
  render();
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
    else if (value == null || !available(f, { x: nx, y: ny }, crop)) rgb = (x + y) % 4 < 2 ? [19, 27, 37] : [29, 38, 49];
    else {
      if (mode === 'wavelength') {
        const t = Math.max(0, Math.min(1, (value - report.config.low_um) / (report.config.high_um - report.config.low_um)));
        rgb = [60 + 170 * t, 145 - 80 * t, 225 - 160 * t];
      } else { rgb = plateRGB(stretch(value - background, limits), $('palette').value !== 'positive'); }
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
  ctx.fillText('X nativo · pixel', imageView.left + imageView.width / 2 - 40, imageView.top + imageView.height + 36);
  ctx.fillText('Y', imageView.left - 28, imageView.top - 8);
  const bandOnly = mode === 'masked' || mode === 'wavelength';
  const stars = starsFor(f, scope, bandOnly, gaiaAvailable && $('gaia-overlay').checked);
  ctx.save(); ctx.beginPath(); ctx.rect(imageView.left, imageView.top, imageView.width, imageView.height); ctx.clip();
  if ($('overlays').checked) {
    ctx.strokeStyle = photometric && $('palette').value !== 'positive' ? '#0a7a8f' : '#72d9ee'; ctx.lineWidth = 1.2; ctx.setLineDash([5, 4]);
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
  ctx.strokeStyle = photometric && $('palette').value !== 'positive' ? '#a77600' : '#f4ce75'; ctx.lineWidth = 1;
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
  $('field-label').textContent = `${crop.w} × ${crop.h} px${arcsec ? ` · ≈ ${number(crop.w * arcsec / 60, 1)}′` : ''} · ${scope === 'target' ? 'recorte na previsão MPC/MOST' : 'campo FITS disponível'}`;
  $('plot-note').textContent = `Gaia: ${gaiaAvailable ? `${stars.length} fonte(s) compatível(is) nesta vista` : 'indisponível; sem pontos sobrepostos'}. ${f.plot?.counts?.excluded_from_image ?? 0} registro(s) fora da cobertura excluído(s). Áreas hachuradas não possuem dado aceito.`;
  $('stretch-note').textContent = limits ? `Asinh · escala comum no detector D${f.detector ?? 4} · fundo removido só no display · ${number(limits.lo, 4)} a ${number(limits.hi, 4)} MJy/sr.` : mode === 'mask' ? 'Cores representam motivos de exclusão e flags de revisão.' : `Centros de banda CWAVE · ${number(report.config.low_um)}–${number(report.config.high_um)} μm.`;
}
function plot() {
  const c = $('photometry'), ctx = c.getContext('2d'); ctx.clearRect(0, 0, c.width, c.height);
  const axis = $('plot-axis').value === 'time' ? 'time' : 'spectrum';
  const points = spectralPoints(report.frames, axis);
  ctx.font = '13px system-ui'; ctx.fillStyle = '#9baeba';
  if (!points.length) { ctx.fillText('Sem aberturas válidas para medir o fluxo nesta seleção.', 20, 100); return; }
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
  ctx.fillStyle = '#9baeba'; ctx.fillText(axis === 'spectrum' ? 'λ CWAVE · barras: CBAND e ±1σ' : `UTC · ${new Date(xlo).toISOString().slice(0, 10)} a ${new Date(xhi).toISOString().slice(0, 10)}`, 80, 292);
}
function render() {
  if (!report?.frames.length) return; const f = report.frames[index], m = f.measurement;
  $('frame-band').textContent = `D${f.detector ?? 4} · ${number(f.central_wavelength_um ?? m.lambda_um, 4)} μm`;
  $('frame-label').textContent = `${index + 1} / ${report.frames.length}`; $('time').value = index;
  $('epoch').textContent = `${f.utc} UTC · ${f.source} · pixels nativos / WCS próprio`;
  $('fits').href = `/${f.fits}`;
  $('metrics').replaceChildren(...[[`${number(f.accepted_fraction * 100, 1)}%`, 'pixels aceitos no recorte'], [`${number(m.coverage * 100, 1)}%`, 'cobertura da abertura'], [number(m.flux_ujy, 1), 'μJy na abertura prevista']].map(([value, label]) => { const card = node('div', '', 'metric'); card.append(node('strong', value), node('span', label)); return card; }));
  $('measurements').replaceChildren(...report.frames.map((frame, i) => {
    const a = frame.measurement, tr = node('tr', '', i === index ? 'selected' : ''); tr.tabIndex = 0;
    [`D${frame.detector ?? 4}`, frame.utc, number(a.lambda_um, 4), number(a.bandwidth_um, 4), a.flux_ujy == null ? '—' : `${number(a.flux_ujy)} ± ${number(a.error_ujy)}`, number(a.snr), `${number(100 * a.coverage, 1)}%`, statuses[a.status] || a.status].forEach(s => tr.append(node('td', s)));
    const upstream = report.skyshift_photometry?.rows.find(r => r.frame_id === frame.id)?.point;
    tr.append(node('td', !upstream ? 'Não executada' : upstream.ok ? `${number(upstream.flux['2.0'])} ± ${number(upstream.err['2.0'])} μJy` : upstream.why));
    const select = () => { stop(); index = i; render(); }; tr.addEventListener('click', select); tr.addEventListener('keydown', e => { if (e.key === 'Enter') select(); }); return tr;
  }));
  const entries = { 'Alvo RA / Dec': `${number(f.target.ra, 7)}° / ${number(f.target.dec, 7)}°`, 'Origem da posição': f.target.provider || 'Manifesto fornecido', 'Astrometria': f.target.position_status || 'Não verificada', 'Máscara': statuses[m.status] || m.status, 'ZODI subtraído': f.zodi_subtracted ? 'Sim; modelo do FITS' : 'Não', 'Flags de revisão': `${number(100 * f.advisory_fraction, 2)}% dos pixels; preservadas`, 'Calibração': f.calibration.source, 'SHA-256 original': f.input_sha256, 'SHA-256 saída': f.output_sha256 };
  $('metadata').replaceChildren(...Object.entries(entries).flatMap(([k, v]) => [node('dt', k), node('dd', v)]));
  drawImage(); plot();
}
$('time').addEventListener('input', e => { stop(); index = +e.target.value; render(); });
$('play').addEventListener('click', () => {
  if (timer) return stop();
  if (!report?.frames.length) return;
  const sequence = playbackFrames(report.frames, report.frames[index]);
  if (sequence.length < 2) return status('Sem duas exposições no mesmo detector e com CWAVE a até 0,01 μm. Selecione quadros manualmente.');
  $('play').textContent = 'Ⅱ'; $('play').setAttribute('aria-label', 'Pausar exposições');
  timer = setInterval(() => {
    const next = sequence[(sequence.indexOf(report.frames[index]) + 1) % sequence.length];
    index = report.frames.indexOf(next); render();
  }, 1000);
});
document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); });
$('tabs').addEventListener('click', e => { if (!e.target.dataset.mode) return; mode = e.target.dataset.mode; for (const b of $('tabs').children) b.setAttribute('aria-pressed', String(b === e.target)); drawImage(); });
$('overlays').addEventListener('change', drawImage);
$('gaia-overlay').addEventListener('change', drawImage);
$('scope').addEventListener('change', drawImage);
$('contrast').addEventListener('input', drawImage);
$('palette').addEventListener('change', drawImage);
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
  $('channel-id').value = '0'; applyChannel();
});
$('channel-id').addEventListener('change', applyChannel);
for (const key of ['low_um', 'high_um', 'detector']) {
  $('query').elements?.[key]?.addEventListener?.('change', () => { $('channel-id').value = '0'; applyChannel(); });
}
$('sample-select').addEventListener('change', () => {
  const sample = joinedSamples.find(s => s.id === $('sample-select').value);
  if (sample) {
    $('channel-id').value = String(sample.channel_id || 0); applyChannel();
    const form = $('query').elements;
    if (form.start && form.end) {
      form.start.value = sample.utc.slice(0, 10);
      form.end.value = new Date(Date.parse(`${sample.utc}Z`) + 86400000).toISOString().slice(0, 10);
    }
  }
  sampleInfo();
});
$('mpc-search').addEventListener('click', async () => {
  $('mpc-search').disabled = true; $('mpc-status').textContent = 'Consultando API oficial MPC…';
  const waiting = node('option', 'Consultando…'); waiting.value = ''; $('mpc-results').replaceChildren(waiting);
  try {
    const result = await api(`/api/mpc?object=${encodeURIComponent($('query').elements.object.value.trim())}`);
    const empty = node('option', result.status === 'not_found' ? 'Objeto não encontrado' : 'Selecione a identificação'); empty.value = '';
    $('mpc-results').replaceChildren(empty, ...result.items.map(item => {
      const option = node('option', `${item.identifier} · ${item.name || item.designation || 'Sem nome'}`); option.value = item.identifier; return option;
    }));
    if (result.status === 'resolved') {
      $('mpc-results').value = result.items[0].identifier; $('query').elements.object.value = result.items[0].identifier;
    }
    $('mpc-status').textContent = result.status === 'resolved' ? 'Identidade validada no MPC. Imagens serão buscadas no IRSA.' : result.status === 'ambiguous' ? 'Identificação ambígua: selecione um resultado.' : 'Nenhum objeto encontrado no MPC.';
  } catch (err) { $('mpc-status').textContent = err.message; } finally { $('mpc-search').disabled = false; }
});
$('mpc-results').addEventListener('change', e => { if (e.target.value) $('query').elements.object.value = e.target.value; });
$('query').elements?.object?.addEventListener?.('input', () => {
  const option = node('option', 'Busque novamente para atualizar a identificação'); option.value = '';
  $('mpc-results').replaceChildren(option); $('mpc-status').textContent = 'Identificação alterada; será validada na API MPC antes da aquisição.';
});
$('image').addEventListener('mousemove', e => {
  if (!report || !imageView) return; const f = report.frames[index], r = e.currentTarget.getBoundingClientRect();
  const p = pixelAt((e.clientX - r.left) / r.width * e.currentTarget.width, (e.clientY - r.top) / r.height * e.currentTarget.height, imageView);
  if (!p) { $('pixel').textContent = 'Fora da área da imagem · nenhuma medida neste ponto.'; return; }
  const { x, y } = p;
  const bits = f.mask[y][x], reasons = Object.entries(report.mask_bits).filter(([, bit]) => bits & bit).map(([name]) => name);
  $('pixel').textContent = `x ${x} · y ${y} · λ ${number(f.wavelength[y][x], 5)} μm · ${number(f.science[y][x], 4)} MJy/sr · ${reasons.join(', ') || 'aceito'}`;
});
$('query').addEventListener('submit', async e => {
  e.preventDefault(); stop(); $('run').disabled = true;
  try {
    const params = Object.fromEntries(new FormData(e.currentTarget));
    for (const k of ['low_um', 'high_um', 'max_exposures', 'detector', 'channel_id']) params[k] = Number(params[k]);
    params.include_context = $('include-context').checked;
    const { job } = await api('/api/run', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(params) });
    for (;;) { const state = await api(`/api/jobs/${job}`); status(state.message, state.status === 'error'); if (state.status === 'error') throw new Error(state.message); if (state.status === 'complete') break; await new Promise(resolve => setTimeout(resolve, 1500)); }
    if (await load()) status('Análise concluída. Confira cobertura, flags e astrometria antes de interpretar as medidas.');
  } catch (err) { status(err.message, true); } finally { $('run').disabled = false; }
});
try {
  try {
    const grid = await api('/api/channels'); channelData = grid.channels || [];
    const all = node('option', 'Todos os 102 canais · janela livre'); all.value = '0';
    $('channel-id').replaceChildren(all, ...channelData.map(c => {
      const option = node('option', `${c.id} · D${c.detector}/${c.subchannel} · ${number(c.center_um, 4)} μm`); option.value = String(c.id); return option;
    })); $('channel-id').value = '0';
  } catch (err) { $('channel-info').textContent = `Tabela de canais indisponível: ${err.message}`; }
  const state = await api('/api/state');
  $('server-note').textContent = state.archive_ready ? `Consulta real habilitada. Calibrações: ${(state.available_detectors || [4]).map(d => `D${d}`).join(', ')}.` : 'Consulta real requer calibrações CWAVE/CBAND locais. Resultados já processados continuam disponíveis.';
  if (state.has_report) { if (await load()) status('Análise carregada. Selecione uma exposição ou inspecione a máscara.'); }
  else status('Servidor pronto. Nenhuma análise carregada.');
} catch (err) { status(`Falha ao acessar o processamento Python: ${err.message}`, true); }
