/* Extend the existing autofill only for the shared ug/uz/tg programme. */
(() => {
  'use strict';
  const controls = new Set(['subject_id', 'grade_level', 'instruction_language', 'education_track']);
  const generatedNames = ['program_title_kz', 'program_title_ru', 'variant_key'];

  function generatedValues(form) {
    const fields = form.elements;
    const subject = fields.namedItem('subject_id');
    const option = subject?.selectedOptions[0];
    const grade = fields.namedItem('grade_level')?.value;
    if (!subject?.value || !grade || !option) return null;
    const track = fields.namedItem('education_track')?.value || '';
    const nameKz = option.dataset.nameKz || option.textContent.trim();
    const nameRu = option.dataset.nameRu || nameKz;
    return {
      program_title_kz: `${nameKz}, ${grade}-сынып, оқыту ұйғыр/өзбек/тәжік тілінде${track ? ', ' + track.toUpperCase() : ''}`,
      program_title_ru: `${nameRu}, ${grade} класс, обучение на уйгурском/узбекском/таджикском языке${track ? ', ' + track.toUpperCase() : ''}`,
      variant_key: `subject-${subject.value}-grade-${grade}-uz_ug_tg${track ? '-' + track : ''}`,
    };
  }

  document.querySelectorAll('form[data-objective-autofill]').forEach(form => {
    const groupSelected = () => form.elements.namedItem('instruction_language')?.value === 'uz_ug_tg';
    let saved = {};
    const remember = () => {
      saved = Object.fromEntries(generatedNames.map(name => [name, form.elements.namedItem(name)?.value || '']));
    };
    const apply = (force = false) => {
      if (!groupSelected()) return;
      const values = generatedValues(form);
      if (!values) return;
      for (const name of generatedNames) {
        const field = form.elements.namedItem(name);
        if (field) field.value = force ? values[name] : (saved[name] || values[name]);
      }
      remember();
    };
    // Existing values from validation errors remain editable and are preserved.
    remember();
    apply();
    form.addEventListener('input', event => {
      if (groupSelected() && generatedNames.includes(event.target.name)) remember();
    });
    form.addEventListener('change', event => {
      if (!groupSelected()) return;
      if (generatedNames.includes(event.target.name)) { remember(); return; }
      // Run after the original autofill handler without replacing it.
      queueMicrotask(() => apply(controls.has(event.target.name)));
    });
    form.querySelector('[data-refresh-generated]')?.addEventListener('click', () => {
      queueMicrotask(() => apply(true));
    });
  });
})();
