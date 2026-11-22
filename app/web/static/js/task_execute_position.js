/* Restore only the current task, after its HTMX fragment has been initialized. */
(() => {
  'use strict';
  const details = document.getElementById('task-execution-details');
  if (!details) return;
  const key = 'school-monitor:task-execute-position:v1';
  const task = () => document.getElementById('selected_task_id')?.value || '';
  const month = () => document.getElementById('month')?.value || '';
  let lastAnchor = null;
  function rememberAnchor(event) {
    const node = event.target instanceof Element ? event.target.closest('[id]') : null;
    if (node && details.contains(node)) lastAnchor = node;
  }
  details.addEventListener('focusin', rememberAnchor);
  details.addEventListener('pointerdown', rememberAnchor);
  document.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const language = form.matches('form.ui-language');
    const saving = form.id === 'system-reports-execute-form' && event.submitter?.value === 'save';
    if (!language && !saving) return;
    if (language) {
      const next = form.querySelector('input[name="next"]');
      if (next) {
        const url = new URL(location.href);
        if (task()) url.searchParams.set('selected_task_id', task());
        if (month()) url.searchParams.set('month', month());
        url.searchParams.delete('success');url.searchParams.delete('error');url.hash = '';
        next.value = url.pathname + url.search;
      }
    }
    const anchor = saving ? document.getElementById('task-execution-actions') : lastAnchor;
    try {
      sessionStorage.setItem(key, JSON.stringify({task: task(), month: month(), time: Date.now(),
        mode: saving ? 'actions' : 'language', id: anchor?.id || '',
        offset: anchor?.getBoundingClientRect().top ?? 0, y: window.scrollY}));
      // The generic language restorer cannot wait for task details to arrive.
      if (language) sessionStorage.removeItem('school-monitor:language-scroll:v1');
    } catch (_) { /* Saving and language switching work without storage. */ }
  }, true);
  let state;
  try {
    state = JSON.parse(sessionStorage.getItem(key));
    sessionStorage.removeItem(key);
  } catch (_) { /* A saved URL fragment still restores the action panel. */ }
  if (!state && new URLSearchParams(location.search).get('success') === 'saved') {
    state = {task: task(), month: month(), time: Date.now(), mode: 'actions'};
  }
  if (!state || state.task !== task() || state.month !== month() ||
      !Number.isFinite(state.time) || Date.now() - state.time < 0 || Date.now() - state.time > 120000) return;
  let stopped = false, queued = false, first = true;
  const observer = new MutationObserver(restore);
  const interruptEvents = ['wheel', 'touchstart', 'pointerdown', 'keydown'];
  function stop() {
    stopped = true;observer.disconnect();
    interruptEvents.forEach(name => window.removeEventListener(name, stop, true));
    document.body.removeEventListener('htmx:afterSettle', restore);
    window.removeEventListener('load', restore);
  }
  function restore() {
    if (stopped || queued) return;
    const anchor = state.mode === 'actions' ? document.getElementById('task-execution-actions') : document.getElementById(state.id);
    if (!details.querySelector('.task-execution-content') ||
        (state.mode === 'actions' && !anchor) ||
        (state.mode === 'language' && state.id && !anchor)) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;if (stopped) return;
      if (anchor && details.contains(anchor)) {
        let parent = anchor.parentElement;
        while (parent && details.contains(parent)) {
          if (parent.tagName === 'DETAILS') parent.open = true;
          parent = parent.parentElement;
        }
        if (state.mode === 'actions') {
          anchor.scrollIntoView({block: 'end', behavior: 'instant'});
        } else {
          const offset = Number.isFinite(state.offset) ? state.offset : 100;
          window.scrollTo({top: Math.max(0, window.scrollY + anchor.getBoundingClientRect().top - offset), behavior: 'instant'});
        }
      } else if (Number.isFinite(state.y)) {
        window.scrollTo({top: Math.max(0, state.y), behavior: 'instant'});
      }
      if (first) { first = false;window.setTimeout(stop, 2500); }
    });
  }
  interruptEvents.forEach(name => window.addEventListener(name, stop, {capture: true, passive: true}));
  observer.observe(details, {subtree: true, childList: true});
  document.body.addEventListener('htmx:afterSettle', restore);
  window.addEventListener('load', restore, {once: true});
  if (document.fonts?.ready) document.fonts.ready.then(restore);
  window.setTimeout(stop, 30000);
  restore();
})();
