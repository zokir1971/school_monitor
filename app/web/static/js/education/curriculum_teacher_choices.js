/* One school list and a compact subject -> teacher-id index; no per-row requests. */
(() => {
  'use strict';
  const data = document.getElementById('curriculum-teacher-choices');
  if (!data) return;
  let payload;
  try { payload = JSON.parse(data.textContent); } catch (_) { return; }
  if (!payload || !Array.isArray(payload.teachers) || !payload.by_subject) return;
  const teachers = new Map(payload.teachers.map(item => [String(item.id), item]));
  const allIds = [...teachers.keys()];
  const selector = '[data-curriculum-teacher]';
  const subjectFor = select => select.dataset.subjectId || select.closest('form')?.querySelector('[data-teacher-subject]')?.value || '';

  function populate(select, reset = false) {
    if (!(select instanceof HTMLSelectElement) || !select.matches(selector)) return;
    const subject = subjectFor(select);
    const all = select.dataset.showAll === '1';
    const cacheKey = subject + ':' + all;
    if (!reset && select.dataset.choicesReady === cacheKey) return;
    const selected = reset ? '' : select.value;
    const matching = payload.by_subject[subject];
    const ids = subject ? (all ? allIds : (Array.isArray(matching) ? matching.map(String) : [])) : [];
    const selectedIds = new Set(ids);
    // A saved or explicitly selected teacher remains visible when switching filters.
    if (selected && teachers.has(selected) && !selectedIds.has(selected)) ids.unshift(selected);
    const fragment = document.createDocumentFragment();
    for (const id of ids) {
      const item = teachers.get(String(id));
      if (item) fragment.appendChild(new Option(item.label || item.name, String(item.id)));
    }
    while (select.options.length > 1) select.remove(1);
    select.appendChild(fragment);
    select.value = selected;
    select.disabled = !subject;
    select.dataset.choicesReady = cacheKey;
    const form = select.closest('form');
    const toggle = form?.querySelector('[data-teacher-toggle]');
    if (toggle) {
      toggle.disabled = !subject;
      toggle.textContent = all ? toggle.dataset.showMatching : toggle.dataset.showAll;
      toggle.setAttribute('aria-pressed', String(all));
    }
    const hint = form?.querySelector('[data-teacher-hint]');
    if (hint) hint.textContent = subject && !ids.length ? hint.dataset.empty : '';
  }

  function onOpen(event) { populate(event.target); }
  document.addEventListener('pointerdown', onOpen, true);
  document.addEventListener('focusin', onOpen, true);
  document.addEventListener('click', event => {
    const toggle = event.target.closest('[data-teacher-toggle]');
    if (!toggle) return;
    const select = toggle.closest('form')?.querySelector(selector);
    if (!select) return;
    select.dataset.showAll = select.dataset.showAll === '1' ? '0' : '1';
    populate(select);
  });
  document.addEventListener('change', event => {
    if (!event.target.matches('[data-teacher-subject]')) return;
    const select = event.target.closest('form')?.querySelector(selector);
    if (select) {
      select.dataset.showAll = '0';
      populate(select, true);
    }
  });
  // The load form changes its subject; fixed curriculum rows stay lazily populated.
  document.querySelectorAll(selector).forEach(select => {
    if (!select.dataset.subjectId) populate(select);
  });
})();
