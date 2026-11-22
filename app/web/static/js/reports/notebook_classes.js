(() => {
  'use strict';
  const root = document.getElementById('notebook-classes');
  const subject = document.getElementById('notebook-subject');
  if (!root || !subject) return;
  const form = root.closest('form');
  const rows = Array.from(root.querySelectorAll('[data-nb-row]'));
  const panels = document.getElementById('notebook-class-scores');
  const template = document.getElementById('notebook-score-template');
  const byKey = new Map(Array.from(panels.querySelectorAll('[data-nb-panel]')).map(p => [p.dataset.nbPanel, p]));
  const ru = document.documentElement.lang === 'ru';
  let ratingLevels = [];
  try { ratingLevels = JSON.parse(document.getElementById('notebook-rating-data')?.textContent || '[]').slice().sort((a,b) => b.from - a.from); } catch (_) {}

  const draftKey = `sm-notebook-v264:${root.dataset.user}:${location.pathname}:${root.dataset.template}`;
  const revision = root.querySelector('[name=notebook_revision]').value;
  let dirty = false;
  function title(panel) {
    const action = panel.open ? (ru ? 'Скрыть таблицу оценивания' : 'Бағалау кестесін жасыру') : (ru ? 'Открыть таблицу оценивания' : 'Бағалау кестесін ашу');
    panel.querySelector('[data-nb-class-title]').textContent = `${panel.dataset.className} — ${action}`;
  }
  function capture() {
    if (!dirty) return;
    try {
      sessionStorage.setItem(draftKey, JSON.stringify({at:Date.now(), revision, subject:subject.value,
        selected:rows.filter(row => row.querySelector('[type=checkbox]').checked).map(row => row.dataset.key),
        values:Array.from(root.querySelectorAll('[data-nb-count]')).map(el => [el.name, el.value]),
        scores:Array.from(root.querySelectorAll('[data-nb-score]:checked')).map(el => [el.name, el.value]),
        panels:Array.from(byKey.values()).map(panel => [panel.dataset.nbPanel, panel.open])}));
    } catch (_) { /* The server draft remains available if tab storage is disabled. */ }
  }
  function restore() {
    let state;
    try {
      state = JSON.parse(sessionStorage.getItem(draftKey));
      sessionStorage.removeItem(draftKey);
    } catch (_) { return; }
    if (!state || state.revision !== revision || Date.now() - state.at > 1800000 || state.at > Date.now() ||
        !Number.isFinite(state.at) || new URL(location.href).searchParams.has('reset_form') ||
        !Array.isArray(state.selected) || !Array.isArray(state.values) || !Array.isArray(state.scores) || !Array.isArray(state.panels)) return;
    if (!Array.from(subject.options).some(option => option.value === state.subject)) return;
    subject.value = state.subject;
    rows.forEach(row => {
      row.querySelector('[type=checkbox]').checked = state.selected.includes(row.dataset.key) && row.dataset.subject === subject.value;
      if (state.panels.some(([key]) => key === row.dataset.key)) panelFor(row);
    });
    update();
    const values = new Map(state.values), scores = new Map(state.scores), open = new Map(state.panels);
    root.querySelectorAll('[data-nb-count]').forEach(el => { if (values.has(el.name)) el.value = values.get(el.name); });
    root.querySelectorAll('[data-nb-score]').forEach(el => { el.checked = scores.get(el.name) === el.value; });
    byKey.forEach((panel, key) => { panel.open = open.get(key) === true; });
    dirty = true;
  }
  function panelFor(row) {
    const key = row.dataset.key;
    if (!byKey.has(key)) {
      const fragment = template.content.cloneNode(true);
      const panel = fragment.querySelector('details');
      panel.dataset.nbPanel = key;
      panel.dataset.className = row.dataset.className;
      panel.open = true;
      title(panel);
      panel.querySelectorAll('[name]').forEach(el => { el.name = el.name.replace('__KEY__', key); });
      byKey.set(key, panel);
      panels.append(fragment);
    }
    return byKey.get(key);
  }
  function update() {
    const totals = {students:0,have:0,missing:0,checked:0,unchecked:0};
    let totalScore = 0, maxScore = 0, validCounts = true, selectedCount = 0, invalid = false;
    for (const row of rows) {
      const box = row.querySelector('[type=checkbox]');
      const visible = row.dataset.subject === subject.value;
      row.hidden = !visible;
      if (!visible) box.checked = false;
      box.disabled = !visible;
      const chosen = visible && box.checked;
      const inputs = Array.from(row.querySelectorAll('[data-nb-count]'));
      inputs.forEach(el => { el.disabled = !chosen; el.setCustomValidity(''); });
      let panel = byKey.get(row.dataset.key);
      if (chosen) panel = panelFor(row);
      if (panel) {
        panel.hidden = !chosen;
        panel.querySelectorAll('input,select,textarea').forEach(el => { el.disabled = !chosen; });
      }
      if (!chosen) continue;
      selectedCount++;
      const students = Number(row.dataset.students);
      totals.students += students;
      const rawCounts = inputs.map(el => el.value.trim());
      const counts = rawCounts.map(raw => raw === '' ? null : Number(raw));
      const validNumbers = inputs.every((el, i) => !el.validity.badInput && (
        rawCounts[i] === '' || (/^[0-9]+$/.test(rawCounts[i]) && Number.isSafeInteger(counts[i]) && counts[i] <= students)
      ));
      inputs.forEach((el, i) => {
        const other = counts[1 - i];
        el.max = String(other !== null && Number.isSafeInteger(other) && other >= 0 ? Math.max(0, students - other) : students);
      });
      const sum = counts.every(v => v !== null) ? counts[0] + counts[1] : null;
      const invalidRow = !validNumbers || (sum !== null && sum > students);
      invalid ||= invalidRow;
      if (invalidRow) inputs.forEach(el => el.setCustomValidity(ru ? 'Введите целые неотрицательные числа. Сумма не должна превышать численность класса.' : 'Теріс емес бүтін сандарды енгізіңіз. Қосынды сыныптағы оқушылар санынан аспауы тиіс.'));
      const checked = !invalidRow ? sum : null;
      row.querySelector('[data-nb-checked]').textContent = checked ?? '—';
      row.querySelector('[data-nb-unchecked]').textContent = checked === null ? '—' : students - checked;
      validCounts &&= checked !== null;
      if (checked !== null) {
        totals.have += counts[0]; totals.missing += counts[1]; totals.checked += checked; totals.unchecked += students - checked;
      }
      let score = 0, maximum = 0;
      panel.querySelectorAll('[data-nb-score-group]').forEach(group => {
        const radios = Array.from(group.querySelectorAll('[data-nb-score]'));
        radios.forEach(el => el.setCustomValidity(''));
        const checkedScore = radios.find(el => el.checked);
        score += checkedScore ? Number(checkedScore.value) : 0;
        maximum += Math.max(0, ...radios.map(el => Number(el.value)));
      });
      title(panel);
      panel.querySelector('[data-nb-class-total]').textContent = `${score} / ${maximum}`;
      totalScore += score; maxScore += maximum;
    }
    root.querySelector('[data-nb-error]').hidden = !invalid;
    root.querySelectorAll('[data-nb-total]').forEach(el => {
      const key = el.dataset.nbTotal;
      el.textContent = selectedCount && (key === 'students' || validCounts) ? totals[key] : '—';
    });
    const selectedRows = rows.filter(row => !row.hidden && row.querySelector('[type=checkbox]').checked);
    document.querySelector('[name=info_class_name]').value = selectedRows.map(row => row.dataset.className).join(', ');
    document.querySelector('[name=info_subject_name]').value = subject.value ? subject.selectedOptions[0].textContent : '';
    const percent = maxScore ? Math.round(totalScore * 100 / maxScore) : 0;
    document.getElementById('total_score').value = totalScore;
    document.getElementById('max_score').value = maxScore;
    document.getElementById('percent').value = percent;
    const rating = ratingLevels.find(level => percent >= level.from);
    document.getElementById('level_display').value = rating ? (ru ? rating.label_ru : rating.label_kz) : '—';
  }
  const changed = () => { dirty = true; update(); capture(); };
  root.addEventListener('click', event => {
    if (event.target.closest('input,label,button,a,select,textarea')) return;
    const cell = event.target.closest('[data-nb-score-cell]');
    const radio = cell?.querySelector('[data-nb-score]');
    if (radio && !radio.disabled) { radio.focus({preventScroll:true}); radio.click(); }
  });
  root.addEventListener('change', changed);
  root.addEventListener('input', changed);
  root.addEventListener('toggle', event => {
    if (event.target.matches('[data-nb-panel]')) { title(event.target); capture(); }
  }, true);
  document.addEventListener('sm:planning-draft-restored', update);
  document.addEventListener('submit', event => {
    if (event.target.matches('form.ui-language')) { dirty = true; capture(); }
  }, true);
  window.addEventListener('pagehide', capture);
  window.addEventListener('pageshow', update);
  form.addEventListener('submit', event => {
    update();
    const invalidCount = rows.filter(row => !row.hidden && row.querySelector('[type=checkbox]').checked)
      .flatMap(row => Array.from(row.querySelectorAll('[data-nb-count]'))).find(el => !el.checkValidity());
    if (invalidCount) {
      event.preventDefault(); invalidCount.focus(); invalidCount.reportValidity(); return;
    }
    if (event.submitter?.value !== 'complete') return;
    const chosen = rows.filter(r => r.querySelector('[type=checkbox]').checked && !r.hidden);
    if (!chosen.length) { event.preventDefault(); subject.focus(); return; }
    for (const row of chosen) {
      for (const el of [...row.querySelectorAll('[data-nb-count]'), ...Array.from(panelFor(row).querySelectorAll('[data-nb-score-group]')).filter(group => !group.querySelector(':checked')).map(group => group.querySelector('[data-nb-score]'))]) {
        if (el.value === '' || (el.type === 'radio' && !el.checked)) {
          event.preventDefault(); panelFor(row).open = true; el.focus();
          el.setCustomValidity(ru ? 'Заполните поле перед подписанием.' : 'Қол қою алдында өрісті толтырыңыз.');
          el.reportValidity(); return;
        }
      }
    }
  });
  restore();
  update();
})();
