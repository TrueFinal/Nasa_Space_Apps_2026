// Contextual glossary: plain-language explanations beside the actual controls.
const definitions = [
  ['#ra', 'Right Ascension (RA)', 'The sky’s east–west coordinate, like longitude on a map. Enter degrees (0–360) or hours, minutes and seconds, such as 08:55:10.831.'],
  ['#dec', 'Declination (Dec)', 'The sky’s north–south coordinate, like latitude. It runs from −90° to +90°. A minus sign means south of the celestial equator.'],
  ['#fov', 'Field of view', 'How much sky fits in the image. The ″ symbol means arcseconds: 60″ = 1 arcminute. A larger field helps follow fast-moving objects but downloads more data.'],
  ['#detector', 'Detector', 'One of SPHEREx’s six infrared cameras. Each covers a different range of invisible light. Changing the detector can change a source’s appearance even when it has not changed over time.'],
  ['#band', 'Spectral channel and µm', 'A channel is one narrow slice of infrared light, among 102. µm means micrometres, the unit for wavelength. A detector combines a wider range; a single channel may have gaps in coverage.'],
  ['[data-mode="mean"]', 'Mean stack', 'Combines the selected frames into an average image, giving more weight to less noisy measurements. This can reveal faint stationary sources. A moving object may look spread out or less distinct.'],
  ['[data-mode="difference"]', 'Difference image', 'Subtracts the chosen reference image to highlight changes. Dark means brighter than the reference, light means dimmer, and mid-gray means no change. Noise, image artifacts and different wavelength coverage can also leave marks.'],
  ['[data-mode="trail"]', 'Motion trail', 'Overlays the chosen frames, keeping the brightest value at each sky position. A moving source may appear in several positions. It does not draw or confirm a path; frames only hours apart can look unchanged.'],
  ['[data-mode="map"]', 'WISE and Gaia context', 'Compares the field with other surveys. WISE supplies older infrared images; Gaia supplies star positions. These overlays are context, not additional SPHEREx animation frames. External map services may be unavailable.'],
  ['#spectrum', 'Exploratory aperture spectrum', 'A chart of brightness at different infrared wavelengths. Click the image to choose a small measurement area. These estimates mix observation dates and use approximate wavelengths, so they cannot by themselves identify an object or molecule.'],
];

export function installHelp() {
  let active = null, closeTimer;
  function close() {
    clearTimeout(closeTimer);
    if (active) { active.popup.hidden = true; active.button.setAttribute('aria-expanded', 'false'); }
    active = null;
  }
  function position(entry) {
    const box = entry.button.getBoundingClientRect(), tip = entry.popup;
    tip.style.left = '12px'; tip.style.top = '12px';
    const width = tip.offsetWidth, height = tip.offsetHeight;
    tip.style.left = Math.max(12, Math.min(innerWidth-width-12, box.left))+'px';
    const below = box.bottom+8;
    tip.style.top = Math.max(12, below+height<innerHeight-12 ? below : box.top-height-8)+'px';
  }
  function show(entry) {
    clearTimeout(closeTimer);
    if (active !== entry) close();
    active = entry; entry.popup.hidden = false;
    entry.button.setAttribute('aria-expanded', 'true'); position(entry);
  }
  function later(entry) {
    closeTimer = setTimeout(() => {
      if (active === entry && !entry.button.matches(':hover') && !entry.popup.matches(':hover') && document.activeElement !== entry.button) close();
    }, 100);
  }
  for (const [selector, title, explanation] of definitions) {
    const control = document.querySelector(selector);
    if (!control) continue;
    const button = document.createElement('button');
    button.type='button'; button.className='term-help'; button.textContent='?';
    button.setAttribute('aria-label', 'Explain '+title); button.setAttribute('aria-expanded','false');
    const popup=document.createElement('div'); popup.className='term-tooltip'; popup.hidden=true;
    popup.id='glossary-'+selector.replace(/[^a-z0-9]/gi,''); popup.setAttribute('role','tooltip');
    const heading=document.createElement('strong'), text=document.createElement('p');
    heading.textContent=title; text.textContent=explanation; popup.append(heading,text);
    button.setAttribute('aria-describedby',popup.id); document.body.append(popup);
    const label=control.closest('label');
    if(label) label.insertBefore(button,control);
    else if(control.matches('[data-mode]')) {
      const pair=document.createElement('span');pair.className='mode-with-help';
      control.before(pair);pair.append(control,button);
    }
    else {
      const heading=control.closest('section')?.querySelector('h3');
      if(heading) heading.append(button); else control.before(button);
    }
    const entry={button,popup}; let openOnDown=false;
    button.addEventListener('pointerdown',()=>{openOnDown=active===entry;});
    button.addEventListener('mouseenter',()=>show(entry));
    button.addEventListener('mouseleave',()=>later(entry));
    button.addEventListener('focus',()=>show(entry)); button.addEventListener('blur',()=>later(entry));
    button.addEventListener('click',event=>{
      event.preventDefault(); event.stopPropagation();
      if(event.detail>0 && openOnDown) close(); else show(entry);
    });
    popup.addEventListener('mouseenter',()=>clearTimeout(closeTimer));
    popup.addEventListener('mouseleave',()=>later(entry));
  }
  document.addEventListener('keydown',event=>{if(event.key==='Escape')close();});
  document.addEventListener('click',event=>{if(active&&!active.button.contains(event.target)&&!active.popup.contains(event.target))close();});
  window.addEventListener('resize',close);
  window.addEventListener('scroll',close,{passive:true});
}
