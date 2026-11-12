/* Section links only: never submit the form, reload, or restore/overwrite fields. */
(() => {
  'use strict';
  const nav = document.querySelector('[data-monthly-direction-nav]');
  const page = document.querySelector('.monthly-plan-page');
  if (!nav || !page) return;
  const links = [...nav.querySelectorAll('a[href^="#month-direction-"]')];
  const sections = links.map(link => document.getElementById(link.hash.slice(1))).filter(Boolean);
  const header = document.querySelector('header.header');
  let queued = false;
  let offset = 145;
  function measure() {
    const top = header ? Math.max(0, header.getBoundingClientRect().bottom) + 1 : 0;
    page.style.setProperty('--month-navigation-top', top + 'px');
    offset = top + nav.getBoundingClientRect().height + 12;
    page.style.setProperty('--month-navigation-offset', offset + 'px');
    schedule();
  }
  function highlight() {
    queued = false;
    let active = sections[0];
    for (const section of sections) {
      if (section.getBoundingClientRect().top <= offset + 4) active = section;
      else break;
    }
    for (const link of links) {
      if (active && link.hash === '#' + active.id) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    }
  }
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(highlight);
  }
  for (const link of links) {
    link.addEventListener('click', event => {
      if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const section = document.getElementById(link.hash.slice(1));
      if (!section) return;
      event.preventDefault();
      // Replace only the anchor; retain month, plan and draft-restoration parameters.
      history.replaceState(history.state, '', location.pathname + location.search + link.hash);
      section.scrollIntoView({block: 'start', behavior: 'auto'});
      schedule();
    });
  }
  addEventListener('scroll', schedule, {passive: true});
  addEventListener('resize', measure, {passive: true});
  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(measure);
    observer.observe(nav);
    if (header) observer.observe(header);
  }
  // No initial scrolling: keep existing #month-item links and draft position restoration.
  measure();
})();
