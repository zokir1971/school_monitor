/* One submit per class. Server performs the same validation under the school lock. */
(() => {
  'use strict';
  const forms = [...document.querySelectorAll('[data-class-assignment-form]')];
  const page = document.querySelector('[data-curriculum-year]');
  const key = 'curriculum-other-class-selections:' + [page?.dataset.curriculumSchool,page?.dataset.curriculumUser,page?.dataset.curriculumYear].join(':');
  const labels = new Map();
  try { const data = JSON.parse(document.getElementById('curriculum-teacher-choices')?.textContent || '{}');
    for (const teacher of data.teachers || []) labels.set(String(teacher.id),teacher.label || teacher.name);
  } catch (_) {}
  forms.forEach(form => form.querySelectorAll('select option').forEach(option => { if (option.value) labels.set(option.value,option.textContent); }));
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || 'null'); sessionStorage.removeItem(key);
    if (saved && Date.now() - saved.time >= 0 && Date.now() - saved.time < 300000) {
      for (const draft of saved.forms || []) {
        const form = document.getElementById(draft.id);
        if (!form || form.elements.namedItem('assignment_version')?.value !== draft.version) continue;
        for (const select of form.querySelectorAll('[data-class-teacher]')) {
          const value = draft.values[select.name];
          if (typeof value !== 'string' || (value && !labels.has(value))) continue;
          if (value && ![...select.options].some(option => option.value === value)) select.add(new Option(labels.get(value),value));
          select.value = value;
        }
      }
    }
  } catch (_) {}
  forms.forEach(form => {
    const selects = [...form.querySelectorAll('[data-class-teacher]')];
    const count = form.querySelector('[data-class-assignment-count]');
    const expected = Number(form.dataset.expectedAssignmentCount || selects.length);
    const error = form.querySelector('[data-class-assignment-error]');
    const update = () => {
      const assigned = selects.filter(select => select.value && !select.disabled).length;
      if (count) count.textContent = count.dataset.countLabel + ': ' + assigned + ' / ' + expected;
      selects.forEach(select => select.removeAttribute('aria-invalid'));
      if (error) error.hidden = true;
    };
    form.addEventListener('change', update);
    form.addEventListener('submit', event => {
      const missing = selects.filter(select => !select.value || select.disabled);
      if (!missing.length && selects.length === expected) {
        // A normal POST refreshes the page: retain selections in the other classes.
        try { sessionStorage.setItem(key,JSON.stringify({time:Date.now(),forms:forms.filter(other => other !== form).map(other => ({
          id:other.id,version:other.elements.namedItem('assignment_version').value,
          values:Object.fromEntries([...other.querySelectorAll('[data-class-teacher]')].map(select => [select.name,select.value]))
        }))})); } catch (_) {}
        return;
      }
      event.preventDefault();
      missing.forEach(select => select.setAttribute('aria-invalid','true'));
      if (error) { error.textContent = error.dataset.missingLabel + ' ' + Math.max(missing.length,expected-selects.length); error.hidden = false; }
      if (missing[0]) missing[0].focus();
    });
    update();
  });
  document.querySelectorAll('[data-open-curriculum-class]').forEach(link => link.addEventListener('click', () => {
    const block = document.getElementById(link.hash.slice(1)); if (block) block.open = true;
  }));
})();
