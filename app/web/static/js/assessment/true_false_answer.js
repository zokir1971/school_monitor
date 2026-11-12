/* Wire this adapter into the existing student save/autosave handler. */
window.TrueFalseAnswer = Object.freeze({
  read(root) {
    if (!root?.matches('[data-tf-student]')) throw new Error('Expected TRUE_FALSE answer container');
    if (root.dataset.format === 'legacy') {
      const selected = root.querySelector('input[type="radio"]:checked');
      return selected ? {value: selected.value === 'true'} : {};
    }
    const values = Object.create(null);
    root.querySelectorAll('[data-tf-student-row]').forEach(row => {
      const selected = row.querySelector('input[type="radio"]:checked');
      if (selected) values[row.dataset.statementId] = selected.value === 'true';
    });
    return {values};
  }
});
