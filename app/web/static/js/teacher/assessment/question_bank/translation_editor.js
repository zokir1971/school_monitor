/* Readable translation fields -> existing server-validated text values only. */
(() => {
  const form = document.querySelector('[data-translation-editor]');
  if (!form) return;
  const inputs = [...form.querySelectorAll('input[data-translation-value]')];
  const hidden = new Map(inputs.map(node => [node.name, node]));
  const fields = [...form.querySelectorAll('[data-translation-field]')];
  const read = node => node.tagName === 'TEXTAREA' ? node.value : node.innerText;
  function deriveStatement() {
    for (const statement of form.querySelectorAll('[data-statement-field]')) {
      const output = hidden.get(statement.dataset.statementField);
      if (!output) continue;
      output.value = [...statement.children].map(node => node.dataset.translationField
        ? read(node) : (node.dataset.statementToken || '')).join('').trim();
    }
  }
  for (const field of fields) {
    field.addEventListener('input', () => {
      const name = field.dataset.translationField;
      const value = read(field);
      if (hidden.has(name)) hidden.get(name).value = value;
      // Repeated accepted answers / bank words intentionally share one field.
      for (const other of fields) {
        if (other === field || other.dataset.translationField !== name) continue;
        if (other.tagName === 'TEXTAREA') other.value = value;
        else other.textContent = value;
      }
      deriveStatement();
    });
  }
  form.addEventListener('submit', deriveStatement);
  const save = form.querySelector('[data-translation-save]');
  if (save) save.disabled = false;
})();
