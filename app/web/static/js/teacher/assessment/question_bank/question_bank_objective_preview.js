(() => {
  "use strict";
  const languages = [...document.querySelectorAll('[data-qb-objective-language]')];
  const selects = [...document.querySelectorAll('[data-qb-objective-select]')];
  const validLanguage = value => ['kk','ru','en'].includes(value) ? value : 'kk';
  let language = languages.length ? validLanguage(languages[languages.length-1].value) : null;
  function update() {
    if (language) {
      for (const input of document.querySelectorAll('[data-qb-objective-language-value]')) input.value = language;
      for (const input of languages) input.value = language;
      for (const select of selects) {
        for (const option of select.options) {
          if (!option.value) continue;
          option.textContent = language === 'ru' ? option.dataset.titleRu : option.dataset.titleKz;
        }
      }
    }
    for (const display of document.querySelectorAll('[data-qb-objective-display]')) {
      const selected = language || validLanguage(display.dataset.objectiveDefaultLanguage);
      for (const text of display.children) text.hidden = text.dataset.objectiveDisplayLanguage !== selected;
    }
    for (const group of document.querySelectorAll('[data-qb-objective-previews]')) {
      const select = group.closest('form')?.querySelector('[data-qb-objective-select]') || selects[0];
      const selected = select?.value || '';
      for (const preview of group.children) {
        preview.hidden = preview.dataset.objectivePreviewId !== selected;
        for (const text of preview.querySelectorAll('[data-objective-preview-language]'))
          text.hidden = text.dataset.objectivePreviewLanguage !== (language || 'kk');
      }
    }
  }
  for (const input of languages) input.addEventListener('change', () => { language = validLanguage(input.value); update(); });
  for (const select of selects) select.addEventListener('change', update);
  window.addEventListener('pageshow', update);
  update();
})();
