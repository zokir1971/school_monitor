/* Formula parts: number of parts equals max_score; old single-formula tasks stay legacy. */
(() => {
  let attempts = 0;
  function init() {
    const group = document.getElementById('formula-fields');
    if (!group || group.dataset.formulaPartsReady) return;
    const form = group.closest('form'), type = form.querySelector('[name="question_type"]');
    const score = (window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]')), status = group.querySelector('[data-formula-parts-status]');
    const list = group.querySelector('[data-formula-parts]'), legacyBox = group.querySelector('[data-formula-legacy]');
    const payload = group.querySelector('[data-formula-parts-payload]');
    function block(message) {
      status.textContent = message;
      form.addEventListener('submit', e => { if (type.value === 'formula') e.preventDefault(); }, true);
    }
    let initial = {};
    try {
      const node = document.getElementById('qb-initial-item');
      if (node) initial = JSON.parse(node.dataset.initialItem);
    } catch (_) { block(window.SchoolMonitorI18n.t("qb_d68c84f1d211")); return; }
    const same = initial.question_type === 'formula';
    const legacy = same && !('parts' in (initial.content || {})) && !('formula_score_policy' in (initial.grading_settings || {}));
    const rich = window.QuestionRichEditor;
    if (!legacy && (!rich || typeof rich.init !== 'function' || typeof rich.sync !== 'function' || !window.customElements?.get('math-field'))) {
      if (attempts++ < 100) { setTimeout(init, 50); return; }
      block(window.SchoolMonitorI18n.t("qb_f90115ad6441")); return;
    }
    const rows = [];
    const scoreError = window.SchoolMonitorI18n.t("qb_513f30697975");
    let ownsScoreError = false;
    function addMeaning(row, symbol = '', label = '') {
      const target = row.querySelector('[data-part-meanings]');
      if (target.children.length >= 30) { status.textContent = window.SchoolMonitorI18n.t("qb_f6ee47f1a721"); return; }
      const fragment = group.querySelector('[data-part-meaning-template]').content.cloneNode(true);
      const item = fragment.querySelector('[data-part-meaning]');
      const symbolField = item.querySelector('[data-part-symbol]');
      for (const button of item.querySelectorAll('[data-symbol-insert]')) {
        button.addEventListener('click', () => {
          symbolField.value = button.dataset.symbolInsert;
          symbolField.focus();
          symbolField.dispatchEvent(new Event('input', {bubbles: true}));
        });
      }
      item.querySelector('[data-part-meaning-label]').value = label;
      item.querySelector('[data-part-remove-meaning]').addEventListener('click', () => {
        item.remove(); if (!target.children.length) addMeaning(row);
      });
      target.append(item);
      // Template clones are inert until connected. Upgrade before setting value;
      // otherwise an own .value property can shadow MathLive's real setter.
      window.customElements.upgrade(symbolField);
      symbolField.value = symbol;
    }
    function add(part = null, key = null) {
      const fragment = group.querySelector('[data-formula-part-template]').content.cloneNode(true);
      const row = fragment.querySelector('[data-formula-part]');
      let id = part?.id;
      if (!id) { let n = rows.length + 1; while (rows.some(r => r.dataset.id === `F${n}`)) n++; id = `F${n}`; }
      row.dataset.id = id;
      row.originalOptions = part?.meaning_options || [];
      const prompt = row.querySelector('[data-formula-prompt]'), expression = row.querySelector('[data-formula-expression]');
      prompt.dataset.initialSegments = JSON.stringify(part?.segments || []);
      expression.dataset.initialSegments = JSON.stringify(key ? [{type: 'latex', text: key.expression}] : []);
      list.append(row); rows.push(row); rich.init(prompt); rich.init(expression);
      if (part) {
        const optionMap = new Map(part.meaning_options.map(option => [option.value, option.label]));
        for (const symbol of part.variables) {
          const label = optionMap.get(key.variable_meanings[symbol]);
          if (typeof label !== 'string') throw new Error(window.SchoolMonitorI18n.t("qb_7c8227c6651f"));
          addMeaning(row, symbol, label);
        }
        const correct = new Set(Object.values(key.variable_meanings));
        row.querySelector('[data-part-distractors]').value = part.meaning_options.filter(o => !correct.has(o.value)).map(o => o.label).join('\n');
        row.querySelector('[data-part-target]').value = part.target_variable || '';
      } else addMeaning(row);
      row.querySelector('[data-part-add-meaning]').addEventListener('click', () => addMeaning(row));
    }
    try {
      if (same && !legacy) {
        if (initial.grading_settings?.formula_score_policy !== 'per_part_v1' || !Array.isArray(initial.content.parts)
            || !initial.content.parts.length || initial.content.parts.length > 100 || !initial.answer_key?.parts) throw new Error('Invalid formula version');
        for (const part of initial.content.parts) {
          const key = initial.answer_key.parts[part.id];
          if (!key || typeof key.expression !== 'string' || !key.expression.trim() || !Array.isArray(part.variables) || !part.variables.length || part.variables.length > 30 || !Array.isArray(part.meaning_options) || !key.variable_meanings) throw new Error('Invalid formula part');
          add(part, key);
        }
      }
    } catch (_) { block(window.SchoolMonitorI18n.t("qb_830c65fd55a0")); return; }
    group.dataset.formulaPartsReady = '1';
    function count() { const n = Number(score.value); return Number.isInteger(n) && n >= 1 && n <= 100 ? n : null; }
    function refresh() {
      const active = type.value === 'formula';
      group.dataset.formulaPartsActive = String(active && !legacy);
      legacyBox.hidden = !legacy; list.hidden = legacy; payload.disabled = !active || legacy;
      legacyBox.querySelectorAll('input,textarea').forEach(input => {
        input.disabled = !active || !legacy;
        if (!legacy) { input.required = false; input.setCustomValidity(''); }
      });
      if (legacy) { status.textContent = window.SchoolMonitorI18n.t("qb_8222d4d558ad"); return; }
      const n = count();
      if (active) { score.setCustomValidity(n ? '' : scoreError); ownsScoreError = !n; }
      else if (ownsScoreError) {
        if (score.validationMessage === scoreError) score.setCustomValidity('');
        ownsScoreError = false;
      }
      while (active && n && rows.length < n) add();
      rows.forEach((row, index) => {
        const shown = n !== null && index < n; row.hidden = !shown;
        row.querySelector('[data-formula-part-heading]').textContent = window.SchoolMonitorI18n.t("qb_0f36d08c76c5", {p0: (index + 1)});
        row.querySelectorAll('input,textarea').forEach(input => input.disabled = !active || !shown);
        row.querySelectorAll('math-field[data-part-symbol], math-field[data-part-target]').forEach(field => {
          field.readOnly = !active || !shown;
          field.setAttribute('aria-disabled', String(!active || !shown));
          field.tabIndex = active && shown ? 0 : -1;
        });
        row.querySelectorAll('[data-symbol-insert]').forEach(button => button.disabled = !active || !shown);
        row.querySelectorAll('[data-rich-content]').forEach(editor => editor.contentEditable = String(active && shown));
      });
      status.textContent = n ? window.SchoolMonitorI18n.t("qb_6ceeebfe72b1", {p0: (n)}) + (rows.length > n ? window.SchoolMonitorI18n.t("qb_1e5a25f00ef5") : '') : window.SchoolMonitorI18n.t("qb_6e48cc6c5d41");
    }
    function segments(editor) {
      rich.sync(editor); return JSON.parse(editor.querySelector('[data-rich-segments]').value || '[]');
    }
    function collect(row) {
      const prompt = segments(row.querySelector('[data-formula-prompt]'));
      const expressionSegments = segments(row.querySelector('[data-formula-expression]'));
      if ([...prompt, ...expressionSegments].some(s => !['text', 'latex'].includes(s.type) || typeof s.text !== 'string')) throw new Error(window.SchoolMonitorI18n.t("qb_ad5f351ae485"));
      const expression = expressionSegments.map(s => s.text).join('').trim();
      if (!prompt.length || !expression) throw new Error(window.SchoolMonitorI18n.t("qb_b9b9e5277886"));
      const variables = [], meanings = Object.create(null), options = [], byLabel = new Map();
      let next = Math.max(0, ...row.originalOptions.map(o => Number(o.value.slice(1)) || 0));
      const old = new Map(row.originalOptions.map(o => [o.label, o.value]));
      function option(label) {
        label = label.trim(); if (!label || label.length > 200) throw new Error(window.SchoolMonitorI18n.t("qb_82b7cf0990fa"));
        if (!byLabel.has(label)) { const value = old.get(label) || `M${++next}`; byLabel.set(label, value); options.push({value, label}); }
        return byLabel.get(label);
      }
      for (const item of row.querySelectorAll('[data-part-meaning]')) {
        const symbol = item.querySelector('[data-part-symbol]').value.trim();
        if (!symbol || symbol.length > 80 || variables.includes(symbol)) throw new Error(window.SchoolMonitorI18n.t("qb_05aae3836be6"));
        variables.push(symbol); meanings[symbol] = option(item.querySelector('[data-part-meaning-label]').value);
      }
      if (!variables.length) throw new Error(window.SchoolMonitorI18n.t("qb_3ba873c675ff"));
      row.querySelector('[data-part-distractors]').value.split(/\r?\n/).filter(s => s.trim()).forEach(option);
      if (options.length > 50) throw new Error(window.SchoolMonitorI18n.t("qb_49b5a1c0cf04"));
      const originalRank = new Map(row.originalOptions.map((option, index) => [option.value, index]));
      options.sort((a, b) => (originalRank.get(a.value) ?? Infinity) - (originalRank.get(b.value) ?? Infinity));
      const part = {id: row.dataset.id, segments: prompt, variables, meaning_options: options};
      const target = row.querySelector('[data-part-target]').value.trim();
      if (target) { if (!variables.includes(target)) throw new Error(window.SchoolMonitorI18n.t("qb_064a3c27c355")); part.target_variable = target; }
      return [part, {expression, variable_meanings: meanings}];
    }
    score.addEventListener('input', refresh); score.addEventListener('change', refresh); type.addEventListener('change', refresh);
    form.addEventListener('submit', event => {
      if (type.value !== 'formula' || legacy) return;
      try {
        refresh(); const n = count(); if (!n) throw new Error(window.SchoolMonitorI18n.t("qb_6e48cc6c5d41"));
        const parts = [], answers = {};
        rows.slice(0, n).forEach(row => { const [part, key] = collect(row); parts.push(part); answers[part.id] = key; });
        payload.value = JSON.stringify({parts, answers}); payload.disabled = false;
      } catch (error) { event.preventDefault(); status.textContent = error.message; }
    }, true);
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 0)); else setTimeout(init, 0);
})();
