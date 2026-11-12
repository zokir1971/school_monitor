/* Preserve position for one interface-language navigation in this tab. */
(() => {
  'use strict';
  const key = 'school-monitor:language-scroll:v1';
  const destination = value => {
    const url = new URL(value, location.href);
    if (url.origin !== location.origin) return null;
    return url.pathname + url.search;
  };
  document.addEventListener('submit', event => {
    const form = event.target;
    if (!form.matches('form.ui-language')) return;
    try {
      const next = form.querySelector('input[name="next"]');
      const path = destination(next ? next.value : location.href);
      if (!path) return;
      sessionStorage.setItem(key, JSON.stringify({path, x: window.scrollX,
        y: window.scrollY, time: Date.now()}));
    } catch (_) { /* Language switching also works when storage is disabled. */ }
  }, true);

  let saved;
  try {
    const raw = sessionStorage.getItem(key);
    sessionStorage.removeItem(key); // Never affect a later unrelated navigation.
    saved = JSON.parse(raw);
  } catch (_) { return; }
  if (!saved || saved.path !== destination(location.href) ||
      !Number.isFinite(saved.x) || !Number.isFinite(saved.y) ||
      !Number.isFinite(saved.time) || saved.x < 0 || saved.y < 0 ||
      Date.now() - saved.time > 120000 || saved.time > Date.now()) return;

  const start = () => {
    let stopped = false;
    let observer;
    const events = ['wheel', 'touchstart', 'pointerdown', 'keydown'];
    const stop = () => {
      if (stopped) return;
      stopped = true;
      if (observer) observer.disconnect();
      events.forEach(name => window.removeEventListener(name, stop, true));
      window.removeEventListener('load', restore);
    };
    const restore = () => {
      if (stopped) return;
      // Override page-level smooth scrolling for this restoration only.
      const style = document.documentElement.style;
      const previous = style.scrollBehavior;
      style.scrollBehavior = 'auto';
      window.scrollTo({left: saved.x, top: saved.y, behavior: 'instant'});
      style.scrollBehavior = previous;
    };
    events.forEach(name => window.addEventListener(name, stop, {capture: true, passive: true}));
    restore();
    window.addEventListener('load', restore, {once: true});
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(restore);
    if (typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(restore);
      observer.observe(document.body);
    }
    // Images/fonts can change document height. Stop promptly on user input.
    window.setTimeout(stop, 2500);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
  else start();
})();
