/* Use the existing radio change handlers for scores and totals. */
(() => {
  'use strict';
  document.addEventListener('click', event => {
    if (!(event.target instanceof Element)) return;
    const cell = event.target.closest('td[data-report-score-cell]');
    if (!cell) return;
    // A direct control/label click already has its native activation behavior.
    if (event.target.closest('input, label, button, a, select, textarea')) return;
    const radio = cell.querySelector('input[type="radio"][name^="score_"]');
    if (!radio || radio.matches(':disabled')) return;
    radio.focus({preventScroll: true});
    radio.click();
  });
})();
