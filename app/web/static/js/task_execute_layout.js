/* Navigation and presentation only. Existing forms and task_execute.js own workflow. */
(() => {
  'use strict';
  const page = document.querySelector('.task-execution-page');
  const details = document.getElementById('task-execution-details');
  const nav = document.querySelector('[data-task-execution-nav]');
  if (!page || !details || !nav) return;
  const list = nav.querySelector('.task-execution-nav__links');
  const header = document.querySelector('header.header');
  let sections = [], offset = 125, queued = false, rebuilding = false;
  function measure() {
    const top = header ? Math.max(0, header.getBoundingClientRect().bottom) + 1 : 0;
    page.style.setProperty('--task-layout-top', top + 'px');
    offset = top + (nav.hidden ? 0 : nav.getBoundingClientRect().height) + 12;
    page.style.setProperty('--task-layout-offset', offset + 'px');
  }
  function highlight() {
    let active = sections[0];
    for (const section of sections) {
      if (section.getBoundingClientRect().top <= offset + 4) active = section;
      else break;
    }
    for (const link of list.querySelectorAll('a')) {
      if (active && link.hash === '#' + active.id) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    }
  }
  function rebuild() {
    sections = [...details.querySelectorAll('[data-task-section]')].filter(section => section.getClientRects().length > 0);
    const fragment = document.createDocumentFragment();
    for (const section of sections) {
      const link = document.createElement('a');
      link.href = '#' + section.id;
      link.textContent = section.dataset.sectionLabel;
      fragment.appendChild(link);
    }
    list.replaceChildren(fragment);
    nav.hidden = sections.length === 0;
    measure();
    highlight();
  }
  function schedule(rebuildNeeded = false) {
    rebuilding = rebuilding || rebuildNeeded;
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      if (rebuilding) { rebuilding = false; rebuild(); }
      else highlight();
    });
  }
  nav.addEventListener('click', event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href^="#task-section-"]');
    if (!link) return;
    const section = document.getElementById(link.hash.slice(1));
    if (!section || !section.getClientRects().length) return;
    event.preventDefault();
    history.replaceState(history.state, '', location.pathname + location.search + link.hash);
    section.scrollIntoView({block: 'start', behavior: 'auto'});
    schedule();
  });
  document.body.addEventListener('htmx:afterSwap', event => { if (event.target === details) schedule(true); });
  details.addEventListener('change', () => schedule(true));
  if ('MutationObserver' in window) {
    new MutationObserver(() => schedule(true)).observe(details, {subtree: true, childList: true, attributes: true, attributeFilter: ['hidden', 'style']});
  }
  addEventListener('scroll', () => schedule(), {passive: true});
  addEventListener('resize', () => { measure(); schedule(); }, {passive: true});
  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(() => { measure(); schedule(); });
    observer.observe(nav);
    if (header) observer.observe(header);
  }
  // Do not scroll on initialization or an HTMX refresh: retain the draft's position.
  rebuild();
})();
