(() => {
  'use strict';
  const form = document.getElementById('lo-reference-form');
  if (!form) return;
  for (const section of form.querySelectorAll('[data-objective-language]')) {
    const editor = section.querySelector('[data-rich-editor]');
    const has = section.querySelector('[data-has-formula]');
    const reviewed = section.querySelector('[data-formula-reviewed]');
    const snapshot = segments => JSON.stringify(segments.map(s => [s.type, s.text]));
    let previous = snapshot(JSON.parse(editor.dataset.initialSegments));
    const toggle = () => { reviewed.disabled = !has.checked; if (!has.checked) reviewed.checked = false; };
    editor.addEventListener('objective:rich-sync', event => {
      const current = snapshot(event.detail);
      if (current !== previous) reviewed.checked = false;
      previous = current;
      if (event.detail.some(segment => segment.type === 'latex')) has.checked = true;
      toggle();
    });
    has.addEventListener('change', () => { reviewed.checked = false; toggle(); });
    toggle();
  }
  form.addEventListener('submit', event => {
    const error = document.getElementById('lo-edit-error');
    try {
      if (!window.ObjectiveRichEditor) throw new Error(window.SchoolMonitorI18n.t("ed_d7e58b39f2e6"));
      const row = {is_active: document.getElementById('lo-active').checked};
      for (const section of form.querySelectorAll('[data-objective-language]')) {
        const lang = section.dataset.objectiveLanguage;
        const editor = section.querySelector('[data-rich-editor]');
        window.ObjectiveRichEditor.sync(editor);
        const segments = JSON.parse(editor.querySelector('[data-rich-segments]').value);
        row['title_segments_'+lang] = segments;
        row['title_'+lang] = editor.querySelector('[data-rich-plain-value]').value;
        row['has_formula_'+lang] = section.querySelector('[data-has-formula]').checked;
        row['formula_reviewed_'+lang] = section.querySelector('[data-formula-reviewed]').checked;
        if (lang === 'kz' && !row.title_kz.trim()) throw new Error(window.SchoolMonitorI18n.t("ed_f0b4e48ed648"));
        if (row['has_formula_'+lang] && (!segments.some(s => s.type === 'latex') || !row['formula_reviewed_'+lang]))
          throw new Error(lang.toUpperCase()+window.SchoolMonitorI18n.t("ed_05d1da421c05"));
      }
      document.getElementById('lo-objective-json').value = JSON.stringify(row);
      error.hidden = true;
    } catch (failure) { event.preventDefault(); error.textContent = failure.message; error.hidden = false; }
  });
})();
