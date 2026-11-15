// Contextual glossary: plain-language explanations beside the actual controls.
const definitions = [
  ['#ra', 'Right Ascension (RA)', 'The sky’s east–west coordinate, like longitude on a map. Enter degrees (0–360) or hours, minutes and seconds, such as 08:55:10.831.'],
  ['#dec', 'Declination (Dec)', 'The sky’s north–south coordinate, like latitude. It runs from −90° to +90°. A minus sign means south of the celestial equator.'],
  ['#fov', 'Field of view', 'How much sky fits in the image. The ″ symbol means arcseconds: 60″ = 1 arcminute. A larger field helps follow fast-moving objects but downloads more data.'],
  ['#start', 'Start date and UTC', 'The first observation date to include. UTC is the shared world clock used for these observations. Leave dates empty to search all available times.'],
  ['#end', 'End date', 'The last observation date to include, including that day. A longer interval may make slow motion or brightness changes easier to see.'],
  ['#collection', 'Data release', 'A published version of the SPHEREx observations. DR1 and QR3 cover different release ranges. Deep fields are areas observed more often. Search again to request current archive data.'],
  ['#detector', 'Detector', 'One of SPHEREx’s six infrared cameras. Each covers a different range of invisible light. Changing the detector can change a source’s appearance even when it has not changed over time.'],
  ['#band', 'Spectral channel and µm', 'A channel is one narrow slice of infrared light, among 102. µm means micrometres, the unit for wavelength. A detector combines a wider range; a single channel may have gaps in coverage.'],
  ['#group', 'Frame, exposure and visit', 'An exposure is one observation. A frame is one step in the animation: one exposure, a group of nearby visits, or a calendar half-year. Grouping combines observations; it does not guarantee a complete survey.'],
  ['#limit', 'Download selection', 'The archive catalogue and the images you download are separate. All available loads every returned exposure in the chosen detector; a limit takes a sample. List only lets you inspect files one at a time.'],
  ['[data-mode="image"]', 'Observations', 'Shows the same patch of sky at different observation times. Play the sequence or use the arrows to inspect each image. Missing data stay hatched.'],
  ['[data-mode="mean"]', 'Mean stack', 'Combines the chosen frames into an average image, giving less noisy measurements more weight. This can make faint stationary sources clearer, but a moving source can become spread out.'],
  ['[data-mode="trail"]', 'Motion trail', 'Overlays the chosen frames, keeping the brightest value at each sky position. A moving source may appear in several positions. It does not draw or confirm a path; frames only hours apart can look unchanged.'],
  ['[data-mode="difference"]', 'Difference image', 'Subtracts the reference image to reveal changes. Dark means brighter, light means dimmer, and mid-gray means no change. Noise, different wavelengths and image artifacts can also leave marks.'],
  ['[data-mode="map"]', 'WISE and Gaia context', 'Compares the field with other surveys. WISE supplies older infrared images; Gaia supplies star positions. These overlays are context, not additional SPHEREx animation frames. External map services may be unavailable.'],
  ['#stack-first', 'First frame', 'The first image included in the overlay. Frame numbers follow observation time; the dates below show the interval you selected.'],
  ['#stack-count', 'Frame count', 'How many consecutive frames to combine. Check the dates: three frames might span a few hours or several months. Use a wider time interval to look for slow motion.'],
  ['#palette', 'Palette', 'The colours used to display brightness. The default shows faint values as white and bright values as black. Display colours are not the visible colours of the stars.'],
  ['#stretch', 'Contrast', 'Changes how faint and bright details appear on screen. Soft detail brings out a wider range of brightness. This changes the display, not the measured image values.'],
  ['#invert', 'Bright sources dark', 'With this checked, brighter pixels appear darker. Uncheck it to reverse the display. The observations and measurements stay the same.'],
  ['#reference', 'Reference frame', 'The baseline image used by Difference. Comparing a frame with itself gives zero change, shown as mid-gray wherever both images have data.'],
  ['#gaia', 'Gaia DR3', 'A catalogue of stars and their positions, not an infrared photograph. Dots can help identify familiar stars. Their expected positions are adjusted approximately for the observation date.'],
  ['#survey', 'Context survey', 'WISE shows infrared light; DSS shows optical light. Their images come from other dates and telescopes. They can help you recognise the field but are not interchangeable with SPHEREx measurements.'],
  ['#spectrum', 'Exploratory aperture spectrum', 'A chart of brightness at different infrared wavelengths. Click the image to choose a small measurement area. These estimates mix observation dates and use approximate wavelengths, so they cannot by themselves identify an object or molecule.'],
  ['#metadata', 'Observation quality and coverage', 'Coverage tells you how much of the field has accepted data. Rejected pixels failed an instrument or quality check. A hatched area has no usable measurement; it does not mean the sky there is empty.'],
  ['#export', 'Provenance', 'A record of the observations, dates, source files and display choices. Download it to check where a result came from or repeat the same comparison.'],
  ['#export-spectrum', 'CSV', 'A plain-text table that opens in a spreadsheet. The spectrum CSV contains the exploratory brightness measurements; it is not an image.'],
  ['#catalogue', 'Archive catalogue and FITS', 'The list of available observation files. FITS is the standard astronomy image format and includes image data and instrument information. Use View to inspect a file here, or astronomy software to open a downloaded FITS.'],
  ['#targets', 'Saved observed examples', 'These are selected real SPHEREx observations, saved for quick loading. They are not synthetic scenes or the entire archive. Search current data to request a larger or newer selection.'],
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
