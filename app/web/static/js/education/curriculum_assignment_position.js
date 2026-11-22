/* Preserve the working class and viewport across a normal assignment POST. */
(() => {
  'use strict';
  const page = document.querySelector('[data-curriculum-year]');
  if (!page) return;
  const key = 'curriculum-assignment-position:' + page.dataset.curriculumYear;
  const blocks = () => [...page.querySelectorAll('details.curriculum-class-block[id]')];
  let state;
  try {
    const raw = sessionStorage.getItem(key);
    sessionStorage.removeItem(key);
    if (raw) state = JSON.parse(raw);
  } catch (_) { /* Storage can be disabled; the fragment remains a fallback. */ }

  function restore() {
    const fresh = state && Date.now() - state.time >= 0 && Date.now() - state.time < 300000;
    const fragment = location.hash.slice(1);
    const id = fresh ? state.form : fragment;
    const form = id && document.getElementById(id);
    if (!form || !form.matches('[data-assignment-form]')) return;
    if (fresh && Array.isArray(state.open)) {
      const open = new Set(state.open);
      blocks().forEach(block => { block.open = open.has(block.id); });
    }
    const block = form.closest('details.curriculum-class-block');
    if (block) block.open = true;
    const message = page.querySelector('[role="alert"], [role="status"]');
    if (message) {
      const local = message.cloneNode(true);
      local.dataset.assignmentFeedback = '1';
      local.tabIndex = -1;
      form.after(local);
    }
    const align = () => requestAnimationFrame(() => {
      const offset = fresh && Number.isFinite(state.offset) ? state.offset : 80;
      window.scrollTo({top: Math.max(0, window.scrollY + form.getBoundingClientRect().top - offset), behavior: 'instant'});
    });
    align();
    window.addEventListener('pageshow', align, {once: true});
  }

  page.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || !form.matches('[data-assignment-form]')) return;
    let stored = false;
    try {
      sessionStorage.setItem(key, JSON.stringify({time: Date.now(), form: form.id,
        offset: form.getBoundingClientRect().top, open: blocks().filter(block => block.open).map(block => block.id)}));
      stored = true;
    } catch (_) { /* The anchor still returns to the submitted assignment. */ }
    const action = new URL(form.getAttribute('action') || location.href, location.href);
    action.hash = stored ? '' : form.id;
    form.setAttribute('action', action.href);
  });
  restore();
})();
