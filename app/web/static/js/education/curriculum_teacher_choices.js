/* One shared list; populate a native select before the user opens it. */
(() => {
  'use strict';
  const data = document.getElementById('curriculum-teacher-choices');
  if (!data) return;
  let choices;
  try { choices = JSON.parse(data.textContent); } catch (_) { return; }
  if (!Array.isArray(choices)) return;
  function populate(event) {
    const select = event.target;
    if (!(select instanceof HTMLSelectElement) || !select.matches('[data-curriculum-teacher]') || select.dataset.choicesReady) return;
    const selected = select.value;
    const fragment = document.createDocumentFragment();
    for (const item of choices) fragment.appendChild(new Option(item.name, String(item.id)));
    while (select.options.length > 1) select.remove(1);
    select.appendChild(fragment);
    select.value = selected;
    select.dataset.choicesReady = '1';
  }
  document.addEventListener('pointerdown', populate, true);
  document.addEventListener('focusin', populate, true);
})();
