// Contextual onboarding for the sky explorer: a first-visit welcome prompt and a
// 4-step spotlight tour. Answering the prompt (or closing the tour at any step)
// is remembered in localStorage, so the tour never opens automatically again.
const STORAGE_KEY = 'zephyr-lab-tour-v1';
const STEPS = [
  {zone: ['aside'], title: 'Choose your sky',
   text: 'Choose or type your coordinates and spectral range. The five challenge targets load real observations instantly.'},
  {zone: ['.toolbar', '#sky-panel', '.player'], title: 'Watch it change',
   text: 'Press Play to watch the sky change over time, or step through and adjust the frames.'},
  {zone: ['.lower-grid'], title: 'Analyse the science',
   text: 'Analyse the aperture spectrum and the observation quality in real time. Click the sky image to sample a position.'},
  {zone: ['#catalogue'], title: 'Get the raw archive',
   text: 'Download the FITS files or filter additional images of this region.'},
];
const PAD = 10;
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

const storage = {
  seen() { try { return localStorage.getItem(STORAGE_KEY) !== null; } catch { return false; } },
  remember(value) { try { localStorage.setItem(STORAGE_KEY, value); } catch { /* private mode: ignore */ } },
};

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'text') node.textContent = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

function zoneRect(selectors) {
  const rects = selectors.flatMap(s => [...document.querySelectorAll(s)])
    .filter(n => n.offsetParent !== null || getComputedStyle(n).position === 'fixed')
    .map(n => n.getBoundingClientRect()).filter(r => r.width && r.height);
  if (!rects.length) return null;
  const top = Math.min(...rects.map(r => r.top)), left = Math.min(...rects.map(r => r.left));
  const bottom = Math.max(...rects.map(r => r.bottom)), right = Math.max(...rects.map(r => r.right));
  const x0 = Math.max(left - PAD, 4), x1 = Math.min(right + PAD, innerWidth - 4);   // border stays on screen
  return {top: top - PAD, left: x0, width: x1 - x0, height: bottom - top + 2 * PAD};
}

function trapFocus(container, event) {
  if (event.key !== 'Tab') return;
  const items = [...container.querySelectorAll('button:not([disabled])')];
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (event.shiftKey && document.activeElement === first) { last.focus(); event.preventDefault(); }
  else if (!event.shiftKey && document.activeElement === last) { first.focus(); event.preventDefault(); }
}

class Tour {
  constructor() { this.index = 0; this.active = false; this.frame = 0; this.last = ''; }

  start(index = 0) {
    if (this.active) return this.go(index);
    this.active = true;
    this.returnFocus = document.activeElement;
    this.blocker = el('div', {class: 'tour-blocker', 'aria-hidden': 'true'});
    this.spot = el('div', {class: 'tour-spotlight', 'aria-hidden': 'true'});
    this.eyebrow = el('span', {class: 'tour-eyebrow'});
    this.heading = el('h3', {id: 'tour-title'});
    this.body = el('p', {id: 'tour-text'});
    this.back = el('button', {type: 'button', class: 'tour-back', onclick: () => this.go(this.index - 1)});
    this.next = el('button', {type: 'button', class: 'tour-next', onclick: () => this.go(this.index + 1)});
    this.bubble = el('div', {class: 'tour-bubble', role: 'dialog', 'aria-modal': 'true',
      'aria-labelledby': 'tour-title', 'aria-describedby': 'tour-text'}, [
      el('button', {type: 'button', class: 'tour-close', 'aria-label': 'Close tour', text: '✕', onclick: () => this.close()}),
      this.eyebrow, this.heading, this.body,
      el('div', {class: 'tour-actions'}, [this.back, this.next]),
    ]);
    this.onKey = event => {
      if (event.key === 'Escape') this.close();
      else if (event.key === 'ArrowRight') this.go(this.index + 1);
      else if (event.key === 'ArrowLeft' && this.index > 0) this.go(this.index - 1);
      else trapFocus(this.bubble, event);
    };
    document.addEventListener('keydown', this.onKey);
    document.body.append(this.blocker, this.spot, this.bubble);
    document.body.classList.add('tour-open');
    this.go(index);
    const loop = () => { this.place(); if (this.active) this.frame = requestAnimationFrame(loop); };
    this.frame = requestAnimationFrame(loop);
  }

  go(index) {
    if (index >= STEPS.length) return this.close();
    if (index < 0) return;
    this.index = index;
    const step = STEPS[index], n = STEPS.length;
    this.eyebrow.textContent = `STEP ${index + 1} OF ${n}`;
    this.heading.textContent = `${index + 1}. ${step.title}`;
    this.body.textContent = step.text;
    this.back.textContent = '← Back';
    this.back.disabled = index === 0;
    this.next.textContent = index === n - 1 ? `Finish (${n}/${n})` : `Next (${index + 1}/${n}) →`;
    this.bubble.classList.remove('tour-enter'); void this.bubble.offsetWidth; this.bubble.classList.add('tour-enter');
    const target = document.querySelector(step.zone[0]);
    const rect = zoneRect(step.zone);
    if (target && rect) {
      const tall = rect.height > innerHeight * 0.8;
      target.scrollIntoView({block: tall ? 'start' : 'center', behavior: reducedMotion() ? 'auto' : 'smooth'});
    }
    this.next.focus({preventScroll: true});
  }

  place() {
    const rect = zoneRect(STEPS[this.index].zone);
    if (!rect) return;
    const gap = 18, margin = 12, ideal = 340, narrowest = 240;
    const vw = innerWidth, vh = innerHeight;
    // Prefer a side of the zone (the bubble never covers what it explains); shrink the
    // bubble to fit a narrower side column before falling back to above/below/over.
    const roomRight = vw - margin - (rect.left + rect.width) - gap, roomLeft = rect.left - gap - margin;
    let side = null, bw = Math.min(ideal, vw - 2 * margin);
    if (vw >= 700) {
      if (roomRight >= ideal) side = 'right';
      else if (roomLeft >= ideal) side = 'left';
      else if (roomLeft >= narrowest) { side = 'left'; bw = roomLeft; }
      else if (roomRight >= narrowest) { side = 'right'; bw = roomRight; }
    }
    if (this.bubble.style.width !== `${bw}px`) this.bubble.style.width = `${bw}px`;
    const bh = this.bubble.offsetHeight;
    let x, y;
    if (vw < 700) {                                  // phone: bottom sheet, always visible
      x = margin; y = vh - bh - margin;
    } else {
      const visTop = Math.max(rect.top, margin), visBottom = Math.min(rect.top + rect.height, vh - margin);
      const alignY = Math.min(Math.max(visTop, margin), vh - bh - margin);
      if (side === 'right') { x = rect.left + rect.width + gap; y = alignY; }
      else if (side === 'left') { x = rect.left - gap - bw; y = alignY; }
      else if (visBottom + gap + bh <= vh - margin && rect.top + rect.height <= vh) { x = rect.left; y = visBottom + gap; }
      else if (rect.top - gap - bh >= margin) { x = rect.left; y = rect.top - gap - bh; }
      else { x = rect.left + rect.width - bw - margin; y = vh - bh - margin; }   // zone fills the screen
      x = Math.min(Math.max(x, margin), vw - bw - margin);
    }
    const key = [rect.top, rect.left, rect.width, rect.height, x, y].map(Math.round).join();
    if (key === this.last) return;
    this.last = key;
    Object.assign(this.spot.style, {top: `${rect.top}px`, left: `${rect.left}px`,
      width: `${rect.width}px`, height: `${rect.height}px`});
    Object.assign(this.bubble.style, {left: `${x}px`, top: `${y}px`});
  }

  close() {
    if (!this.active) return;
    this.active = false;
    cancelAnimationFrame(this.frame);
    storage.remember('closed');
    document.removeEventListener('keydown', this.onKey);
    document.body.classList.remove('tour-open');
    for (const node of [this.blocker, this.spot, this.bubble]) node.remove();
    this.last = '';
    if (this.returnFocus?.focus) this.returnFocus.focus({preventScroll: true});
  }
}

const tour = new Tour();

function welcome() {
  const previous = document.activeElement;
  const finish = (answer, startTour) => {
    storage.remember(answer);
    document.removeEventListener('keydown', onKey);
    dialog.remove();
    if (startTour) tour.start(0);
    else if (previous?.focus) previous.focus({preventScroll: true});
  };
  const yes = el('button', {type: 'button', class: 'primary', text: 'Yes, show me around',
    onclick: () => finish('accepted', true)});
  const no = el('button', {type: 'button', class: 'subtle', text: "No thanks, I'll explore on my own",
    onclick: () => finish('declined', false)});
  const card = el('div', {class: 'tour-welcome-card', role: 'dialog', 'aria-modal': 'true',
    'aria-labelledby': 'tour-welcome-title', 'aria-describedby': 'tour-welcome-text'}, [
    el('button', {type: 'button', class: 'tour-close', 'aria-label': 'Close', text: '✕',
      onclick: () => finish('declined', false)}),
    el('span', {class: 'eyebrow', text: 'WELCOME TO THE SKY EXPLORER'}),
    el('h3', {id: 'tour-welcome-title', text: 'Is this your first time here?'}),
    el('p', {id: 'tour-welcome-text', text: 'We can walk you through this screen in 4 quick steps. You can leave the tour at any moment.'}),
    el('div', {class: 'tour-welcome-actions'}, [yes, no]),
  ]);
  const dialog = el('div', {class: 'tour-welcome'}, [card]);
  const onKey = event => {
    if (event.key === 'Escape') finish('declined', false);
    else trapFocus(card, event);
  };
  document.addEventListener('keydown', onKey);
  document.body.append(dialog);
  yes.focus();
}

document.getElementById('tour-start')?.addEventListener('click', () => tour.start(0));
if (!storage.seen()) setTimeout(welcome, 400);
