/* No dependencies: keeps mobile links accessible without a separate menu framework. */
for (const header of document.querySelectorAll('.site-header')) {
  const toggle = header.querySelector('.nav-toggle');
  const nav = header.querySelector('.site-nav');
  if (!toggle || !nav) continue;
  const close = (focus = false) => {
    header.classList.remove('menu-open');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Open navigation menu');
    if (focus) toggle.focus();
  };
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    header.classList.toggle('menu-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close navigation menu' : 'Open navigation menu');
  });
  nav.addEventListener('click', e => { if (e.target.closest('a')) close(); });
  document.addEventListener('click', e => { if (!header.contains(e.target)) close(); });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') close(true);
  });
  window.matchMedia('(max-width: 767px)').addEventListener('change', () => close());
}
