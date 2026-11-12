/* Multi-part numeric authoring. Shared create.js and true/false adapter stay intact. */
(() => {
  let attempts = 0;
  function init() {
    const group = document.getElementById('number-fields');
    if (!group || group.dataset.numberReady) return;
    const form = group.closest('form');
    const type = form.querySelector('[name="question_type"]');
    const score = (window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]'));
    const status = group.querySelector('[data-number-status]');
    let initial = {};
    try {
      const source = document.getElementById('qb-initial-item');
      if (source) initial = JSON.parse(source.dataset.initialItem);
    } catch (error) {
      status.textContent = window.SchoolMonitorI18n.t("qb_eb5a04324d8e");
      form.addEventListener('submit', event => { if (type.value === 'number') event.preventDefault(); });
      return;
    }
    const legacy = initial.question_type === 'number' && !('parts' in (initial.content || {}));
    const rich = window.QuestionRichEditor;
    if (!legacy && (!rich || typeof rich.init !== 'function' || typeof rich.sync !== 'function')) {
      if (attempts++ < 100) { setTimeout(init, 50); return; }
      status.textContent = window.SchoolMonitorI18n.t("qb_6222c05fa384");
      form.addEventListener('submit', event => { if (type.value === 'number') event.preventDefault(); });
      return;
    }
    group.dataset.numberReady = '1';
    const legacyBox = group.querySelector('[data-number-legacy]');
    const list = group.querySelector('[data-number-parts]');
    const payload = group.querySelector('[data-number-payload]');
    const rows = [];
    group.querySelector('h3').textContent = window.SchoolMonitorI18n.t("qb_a937865472d5");
    group.querySelector('.qb-answer-builder__header p').textContent = legacy
      ? window.SchoolMonitorI18n.t("qb_16af856802c1")
      : window.SchoolMonitorI18n.t("qb_237aaed7314d");
    function add(part = null, answer = '', tolerance = '') {
      const fragment = group.querySelector('[data-number-row-template]').content.cloneNode(true);
      const row = fragment.querySelector('.qb-number-part');
      let id = part?.id;
      if (!id) { let n = rows.length + 1; while (rows.some(r => r.dataset.id === `N${n}`)) n++; id = `N${n}`; }
      row.dataset.id = id;
      const editor = row.querySelector('[data-rich-editor]');
      editor.dataset.initialSegments = JSON.stringify(part?.segments || []);
      const content = row.querySelector('[data-rich-content]');
      content.id = `number-part-${rows.length + 1}`;
      row.querySelector('[data-number-label]').htmlFor = content.id;
      row.querySelector('[data-number-label]').textContent = window.SchoolMonitorI18n.t("qb_fd54ee393578", {p0: (rows.length + 1)});
      row.querySelector('[data-number-answer]').value = answer;
      row.querySelector('[data-number-tolerance]').value = tolerance;
      row.querySelector('[data-number-unit]').value = part?.unit || '';
      row.querySelectorAll('input[type="text"]').forEach(input => input.addEventListener('input', () => input.setCustomValidity('')));
      list.append(row); rows.push(row); rich.init(editor);
    }
    if (!legacy && initial.question_type === 'number') {
      (initial.content.parts || []).forEach(part => add(part, initial.answer_key?.values?.[part.id] ?? '', initial.grading_settings?.tolerances?.[part.id] ?? ''));
    }
    function count() { const n = Number(score.value); return Number.isInteger(n) && n >= 1 && n <= 100 ? n : null; }
    function refresh() {
      const active = type.value === 'number';
      legacyBox.hidden = !legacy;
      legacyBox.querySelectorAll('input').forEach(input => {
        input.disabled = !active || !legacy;
        input.required = active && legacy && input.name === 'number_answer';
      });
      payload.disabled = !active || legacy;
      list.hidden = legacy;
      if (legacy) return;
      const n = count();
      if (active) score.setCustomValidity(n ? '' : window.SchoolMonitorI18n.t("qb_6e48cc6c5d41"));
      while (active && n && rows.length < n) add();
      rows.forEach((row,index) => {
        const shown = n !== null && index < n;
        row.hidden = !shown;
        row.querySelectorAll('input').forEach(input => input.disabled = !active || !shown);
        row.querySelector('[data-number-answer]').required = active && shown;
        row.querySelector('[data-rich-content]').contentEditable = String(active && shown);
      });
      status.textContent = n ? window.SchoolMonitorI18n.t("qb_8ec6b7bb0be2", {p0: (n)}) + (rows.length > n ? window.SchoolMonitorI18n.t("qb_79bd93480801") : '') : window.SchoolMonitorI18n.t("qb_6e48cc6c5d41");
      if(active && n && window.QBAuthoringScore?.help(form))status.textContent=window.QBAuthoringScore.help(form);
    }
    function number(input, allowBlank = false) {
      const text = input.value.trim().replace(',', '.');
      if (!text && allowBlank) return '0';
      if (text.length > 128 || !/^[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$/.test(text) || !Number.isFinite(Number(text))) {
        input.setCustomValidity(window.SchoolMonitorI18n.t("qb_888eda6be4cf"));
        input.reportValidity(); return null;
      }
      return text;
    }
    score.addEventListener('input', refresh); score.addEventListener('change', refresh); type.addEventListener('change', refresh);
    form.addEventListener('submit', event => {
      if (type.value !== 'number' || legacy) return;
      refresh(); const n = count();
      if (!n) { event.preventDefault(); score.reportValidity(); return; }
      const parts = [], values = Object.create(null), tolerances = Object.create(null);
      for (const row of rows.slice(0,n)) {
        rich.sync(row.querySelector('[data-rich-editor]'));
        const segments = JSON.parse(row.querySelector('[data-rich-segments]').value || '[]');
        if (!segments.length) { event.preventDefault(); status.textContent = window.SchoolMonitorI18n.t("qb_7f9c1e648c92"); row.querySelector('[data-rich-content]').focus(); return; }
        const answer = number(row.querySelector('[data-number-answer]'));
        if (answer === null) { event.preventDefault(); return; }
        const toleranceInput = row.querySelector('[data-number-tolerance]');
        const tolerance = number(toleranceInput, true);
        if (tolerance === null) { event.preventDefault(); return; }
        if (Number(tolerance) < 0) { event.preventDefault(); toleranceInput.setCustomValidity(window.SchoolMonitorI18n.t("qb_a11186881a22")); toleranceInput.reportValidity(); return; }
        const part = {id: row.dataset.id, segments};
        const unit = row.querySelector('[data-number-unit]').value.trim(); if (unit) part.unit = unit;
        parts.push(part); values[part.id] = answer; tolerances[part.id] = tolerance;
      }
      payload.value = JSON.stringify({parts, values, tolerances});
    }, true);
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init,0));
  else setTimeout(init,0);
})();
