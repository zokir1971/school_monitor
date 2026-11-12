/* Separate adapter: keeps the shared eleven-type create.js unchanged. */
(() => {
  let richEditorAttempts = 0;

    function init() {
    const group = document.getElementById("true-false-fields");
    if (!group || group.dataset.tfReady) return;

    const editor = window.QuestionRichEditor;

    if (
        (!editor || typeof editor.init !== "function") &&
        richEditorAttempts < 100
    ) {
        richEditorAttempts++;
        setTimeout(init, 50);
        return;
    }

    group.dataset.tfReady = "1";
    const form = group.closest("form");
    const type = form.querySelector('[name="question_type"]');
    const score = (window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]'));
    const list = group.querySelector('[data-tf-statements]');
    const legacyBox = group.querySelector('[data-tf-legacy]');
    const payload = group.querySelector('[data-tf-payload]');
    const status = group.querySelector('[data-tf-status]');
    const rich = window.QuestionRichEditor;
    let initial = {};
    try {
      const source = document.getElementById('qb-initial-item');
      if (source) initial = JSON.parse(source.dataset.initialItem);
    } catch (error) {
      status.textContent = window.SchoolMonitorI18n.t("qb_eb5a04324d8e");
      form.addEventListener('submit', event => event.preventDefault());
      return;
    }
    const legacy = initial.question_type === 'true_false' && !('statements' in (initial.content || {}));
    const rows = [];
    const title = group.querySelector('h3');
    if (title) title.textContent = legacy ? window.SchoolMonitorI18n.t("qb_4aca0c47be69") : window.SchoolMonitorI18n.t("qb_a3f914a66ca1");
    const help = group.querySelector('.qb-answer-builder__header p');
    if (help) help.textContent = legacy
      ? window.SchoolMonitorI18n.t("qb_8f9699f6b737")
      : window.SchoolMonitorI18n.t("qb_6197b448268e");
    function add(statement = null, value = undefined) {
      const fragment = group.querySelector('[data-tf-row-template]').content.cloneNode(true);
      const row = fragment.querySelector('.qb-tf-row');
      let id = statement?.id;
      if (!id) { let n = rows.length + 1; while (rows.some(r => r.dataset.id === `S${n}`)) n++; id = `S${n}`; }
      row.dataset.id = id;
      const editor = row.querySelector('[data-rich-editor]');
      editor.dataset.initialSegments = JSON.stringify(statement?.segments || []);
      const content = row.querySelector('[data-rich-content]');
      content.id = `tf-statement-${rows.length + 1}`;
      row.querySelector('[data-tf-label]').htmlFor = content.id;
      row.querySelector('[data-tf-label]').textContent = window.SchoolMonitorI18n.t("qb_86aa8d80f499", {p0: (rows.length + 1)});
      const answer = row.querySelector('[data-tf-answer]');
      answer.value = typeof value === 'boolean' ? String(value) : '';
      list.append(row);
      rows.push(row);
      rich.init(editor);
    }
    if (!legacy && !rich) {
      status.textContent = window.SchoolMonitorI18n.t("qb_4cadca61966e");
      form.addEventListener('submit', event => { if (type.value === 'true_false') event.preventDefault(); });
      return;
    }
    if (!legacy && initial.question_type === 'true_false') {
      (initial.content.statements || []).forEach(s => add(s, initial.answer_key?.values?.[s.id]));
    }
    function count() {
      const n = Number(score.value);
      return Number.isInteger(n) && n >= 1 && n <= 100 ? n : null;
    }
    function refresh() {
      const active = type.value === 'true_false';
      legacyBox.hidden = !legacy;
      legacyBox.querySelectorAll('input').forEach(input => {
        input.disabled = !active || !legacy;
        input.required = active && legacy;
      });
      payload.disabled = !active || legacy;
      list.hidden = legacy;
      if (legacy) return;
      const n = count();
      score.setCustomValidity(active && !n ? window.SchoolMonitorI18n.t("qb_6e48cc6c5d41") : '');
      while (active && n && rows.length < n) add();
      rows.forEach((row, index) => {
        const shown = n !== null && index < n;
        row.hidden = !shown;
        row.querySelectorAll('input,select').forEach(input => input.disabled = !active || !shown);
        row.querySelector('[data-tf-answer]').required = active && shown;
        row.querySelector('[data-rich-content]').contentEditable = String(active && shown);
      });
      status.textContent = n
        ? window.SchoolMonitorI18n.t("qb_5c1feccbf126", {p0: (n)}) + (rows.length > n ? window.SchoolMonitorI18n.t("qb_b5b78797f778") : '')
        : window.SchoolMonitorI18n.t("qb_6e48cc6c5d41");
    }
    score.addEventListener('input', refresh);
    score.addEventListener('change', refresh);
    type.addEventListener('change', refresh);
    form.addEventListener('submit', event => {
      if (type.value !== 'true_false' || legacy) return;
      refresh();
      const n = count();
      if (!n) { event.preventDefault(); score.reportValidity(); return; }
      const statements = [], values = {};
      for (const row of rows.slice(0, n)) {
        rich.sync(row.querySelector('[data-rich-editor]'));
        const segments = JSON.parse(row.querySelector('[data-rich-segments]').value || '[]');
        const answer = row.querySelector('[data-tf-answer]');
        if (!segments.length || !answer.value) {
          event.preventDefault();
          status.textContent = window.SchoolMonitorI18n.t("qb_8628bce70a44");
          (!segments.length ? row.querySelector('[data-rich-content]') : answer).focus();
          return;
        }
        statements.push({id: row.dataset.id, segments});
        values[row.dataset.id] = answer.value === 'true';
      }
      payload.value = JSON.stringify({statements, values});
    }, true);
    refresh();
  }
  // Run after the shared create.js and math editor have hydrated the form.
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setTimeout(init, 0);
    });
    } else {
    setTimeout(init, 0);
    }
})();
