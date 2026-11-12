/* Validate manual-review integer budget before making an AI request. */
(() => {
  function init() {
    const form = document.getElementById('qb-ai-generate');
    if (!form || form.dataset.manualIntegerReady) return;
    const type = form.querySelector('[name="question_type"]'), score = form.querySelector('[name="max_score"]');
    const count = form.querySelector('[name="question_count"]');
    if (!type || !score) return;
    form.dataset.manualIntegerReady = '1';
    const original = Object.fromEntries(['min', 'max', 'step'].map(name => [name, score.getAttribute(name)]));
    const message = window.SchoolMonitorI18n.t("qb_8ccd8b24cb77");
    const hint = document.createElement('p'); hint.className = 'qb-help-text'; hint.textContent = window.SchoolMonitorI18n.t("qb_40c7716d790e");
    score.insertAdjacentElement('afterend', hint);
    function refresh() {
      const active = type.value === 'manual_review'; hint.hidden = !active;
      if (!active) {
        for (const [name, value] of Object.entries(original)) { if (value === null) score.removeAttribute(name); else score.setAttribute(name, value); }
        if (score.validationMessage === message) score.setCustomValidity('');
        return true;
      }
      const n = Number(count?.value || 1), minimum = Number.isSafeInteger(n) && n >= 1 ? n : 1;
      score.min = String(minimum); score.max = '99999999'; score.step = '1';
      const value = Number(score.value), valid = Number.isSafeInteger(value) && value >= minimum && value <= 99999999;
      score.setCustomValidity(valid ? '' : message); return valid;
    }
    score.addEventListener('input', refresh); type.addEventListener('change', refresh); count?.addEventListener('input', refresh);
    form.addEventListener('submit', event => { if (!refresh()) { event.preventDefault(); event.stopImmediatePropagation(); score.reportValidity(); } }, true);
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
