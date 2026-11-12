(function () {
  function executionLabel(value) {
    const raw = value == null ? "" : String(value);
    const key = "exec_label:" + raw;
    const label = window.SchoolMonitorI18n.t(key);
    return label === key ? raw : label;
  }

  function safeJsonParse(raw, fallback = {}) {
    try {
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      console.warn("JSON parse error:", e);
      return fallback;
    }
  }

  function resetSelect(selectEl, placeholder, disabled = true) {
    if (!selectEl) return;

    selectEl.innerHTML = "";

    const option = document.createElement("option");
    option.value = "";
    option.textContent = placeholder;
    selectEl.appendChild(option);

    selectEl.disabled = disabled;
    selectEl.value = "";
  }

  function fillSelect(selectEl, items, selectedValue, placeholder) {
    if (!selectEl) return;

    resetSelect(selectEl, placeholder, false);

    (items || []).forEach((item) => {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = executionLabel(item.label);

      if (selectedValue && String(selectedValue) === String(item.code)) {
        option.selected = true;
      }

      selectEl.appendChild(option);
    });
  }

  function renderCheckboxGroup(containerEl, name, items, selectedValues = []) {
    if (!containerEl) return;

    containerEl.innerHTML = "";

    if (!items || !items.length) {
      containerEl.innerHTML =
        window.SchoolMonitorI18n.t("tx_d11b8213bdd3");
      return;
    }

    const normalizedSelected = selectedValues.map(String);

    const group = document.createElement("div");
    group.className = "checkbox-group";

    items.forEach((item) => {
      const wrapper = document.createElement("div");
      wrapper.className = "checkbox-item";

      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = name;
      input.value = item.code;
      input.id = `${name}_${String(item.code).replace(/[^a-zA-Z0-9_-]/g, "_")}`;
      input.checked = normalizedSelected.includes(String(item.code));
      input.dataset.label = item.label || item.code;

      const label = document.createElement("label");
      label.setAttribute("for", input.id);
      label.textContent = executionLabel(item.label) || item.code;

      wrapper.appendChild(input);
      wrapper.appendChild(label);
      group.appendChild(wrapper);
    });

    containerEl.appendChild(group);
  }

  function renderSingleSelect(containerEl, name, items, selectedValue = "") {
    if (!containerEl) return;

    containerEl.innerHTML = "";

    const select = document.createElement("select");
    select.name = name;
    select.id = name;
    select.required = true;

    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = window.SchoolMonitorI18n.t("tx_6a323db2ae5b");
    select.appendChild(defaultOption);

    (items || []).forEach((item) => {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = executionLabel(item.label);

      if (String(selectedValue) === String(item.code)) {
        option.selected = true;
      }

      select.appendChild(option);
    });

    containerEl.appendChild(select);
  }

  function getCheckedValues(root, selector) {
    return Array.from(root.querySelectorAll(selector))
      .filter((el) => el.checked)
      .map((el) => el.value);
  }

  function getCheckedItems(root, selector) {
    return Array.from(root.querySelectorAll(selector))
      .filter((el) => el.checked)
      .map((el) => ({
        value: el.value,
        code: el.value,
        label:
          el.dataset.label ||
          el.getAttribute("data-label") ||
          el.closest(".checkbox-item")?.querySelector("label")?.textContent?.trim() ||
          el.closest("label")?.textContent?.trim() ||
          el.value,
      }));
  }

  function uniqueBy(items, keyFn) {
    const seen = new Set();

    return (items || []).filter((item) => {
      const key = keyFn(item);

      if (seen.has(key)) {
        return false;
      }

      seen.add(key);
      return true;
    });
  }

  function algorithmView(catalog, input) {
    const subjects = new Set(input.subjects.map(String));
    const grades = new Set(input.parallels.map(Number));
    const groupGrades = new Set();
    input.groups.forEach(group => {
      if (!['1_4', '5_9', '10_11'].includes(group)) return;
      const [lo, hi] = group.split('_').map(Number);
      for (let grade = lo; grade <= hi; grade++) groupGrades.add(grade);
    });
    const pairs = catalog.subject_classes || catalog.teaching;
    const subjectClasses = new Set(pairs.filter(row => subjects.has(String(row.subject_id))).map(row => String(row.class_id)));
    const restrictSubjects = ['subject','teacher','parallel','complex'].includes(input.scope) && subjects.size > 0;
    const classes = catalog.classes.filter(row => (!['subject','teacher'].includes(input.scope) || subjects.size > 0) && (!restrictSubjects || subjectClasses.has(String(row.id))) &&
      (input.scope === 'parallel' ? grades.has(Number(row.grade_level))
      : input.scope === 'class' && groupGrades.size ? groupGrades.has(Number(row.grade_level)) : true));
    const explicit = new Set(input.classIds.map(String));
    const selected = classes.filter(row => !explicit.size || explicit.has(String(row.id)));
    const selectedIds = new Set(selected.map(row => String(row.id)));
    const byTeacher = new Map();
    catalog.teaching.forEach(row => {
      if (!selectedIds.has(String(row.class_id)) || !subjects.has(String(row.subject_id))) return;
      const key = String(row.teacher_id);
      if (!byTeacher.has(key)) byTeacher.set(key, {id: key, name: row.full_name, classIds: new Set(), subjectIds: new Set()});
      byTeacher.get(key).classIds.add(String(row.class_id));
      byTeacher.get(key).subjectIds.add(String(row.subject_id));
    });
    return {classes, selected, teachers: Array.from(byTeacher.values()).sort((a,b) => a.name.localeCompare(b.name))};
  }

  function refreshAlgorithmMatrix(root, controlFlow) {
    const host = root.querySelector('[data-algorithm-matrix]');
    if (!host) return;
    const catalog = controlFlow.algorithm_catalog;
    const ru = host.dataset.language === 'ru';
    const data = safeJsonParse(root.querySelector('#task-execution-json-data')?.dataset.state, {});
    const draft = root._algorithmMatrix || (root._algorithmMatrix = {
      classIds: new Set((data.school_class_ids || []).map(String)),
      teacher_ids: new Set((data.teacher_ids || []).map(String)),
      lesson_observation: new Set((data.report_teacher_ids?.lesson_observation || []).map(String)),
      checking_notebooks_table: new Set((data.report_teacher_ids?.checking_notebooks_table || []).map(String))
    });
    const scope = root.querySelector('#control_scope')?.value || '';
    const input = {scope, subjects: getCheckedValues(root, 'input[name="subjects"]'),
      parallels: getCheckedValues(root, 'input[name="parallel_classes"]'), groups: getCheckedValues(root, 'input[name="class_groups"]'),
      classIds: Array.from(draft.classIds)};
    const view = algorithmView(catalog, input);
    const classBox = host.querySelector('[data-algorithm-classes]');
    if (input.subjects.length || !['subject','teacher'].includes(scope)) draft.classIds = new Set([...draft.classIds].filter(id => view.classes.some(row => String(row.id) === id)));
    const classRows = view.classes.map(row => {
      const label = document.createElement('label');
      label.style.cssText = 'display:flex;align-items:center;gap:6px';
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox'; checkbox.name = 'school_class_ids'; checkbox.value = String(row.id);
      checkbox.dataset.algorithmClassId = String(row.id); checkbox.checked = draft.classIds.has(String(row.id)); checkbox.style.width = 'auto';
      const text = document.createElement('span'); text.textContent = row.name;
      label.append(checkbox, text); return label;
    });
    classBox.replaceChildren(...classRows);
    // IDs outside the current parallel/group are not posted and cannot affect the teacher pool.
    input.classIds = view.classes.filter(row => draft.classIds.has(String(row.id))).map(row => String(row.id));
    const filtered = algorithmView(catalog, input);
    host.querySelector('[data-class-hint]').textContent = scope === 'class'
      ? (ru ? 'Отметьте конкретные классы. Это обязательный выбор для контроля класса.' : 'Нақты сыныптарды белгілеңіз. Сыныпты бақылау үшін бұл таңдау міндетті.')
      : (ru ? 'Предлагаются классы, где выбранные предметы есть в учебном плане или действующей нагрузке. Без отметок используются все подходящие классы.' : 'Таңдалған пәндер оқу жоспарында не белсенді жүктемеде бар сыныптар ұсынылады. Белгіленбесе, барлық сәйкес сынып қолданылады.');
    const reports = new Set(getCheckedValues(root, 'input[name="report_types"]'));
    const columns = [];
    if (scope === 'teacher' || reports.has('teacher_analysis')) columns.push(['teacher_ids', ru ? 'Объект контроля' : 'Бақылау нысаны']);
    if (reports.has('lesson_observation')) columns.push(['lesson_observation', ru ? 'Наблюдение урока' : 'Сабақты бақылау']);
    if (reports.has('checking_notebooks_table')) columns.push(['checking_notebooks_table', ru ? 'Проверка тетрадей' : 'Дәптерлерді тексеру']);
    host.querySelector('[data-matrix-teachers]').hidden = columns.length === 0;
    const table = host.querySelector('[data-teacher-matrix]');
    const header = document.createElement('tr');
    [ru ? 'Проверяемый учитель' : 'Тексерілетін мұғалім', ru ? 'Ведёт в выбранных классах' : 'Таңдалған сыныптарда жүргізеді', ...columns.map(column => column[1])].forEach(value => {
      const th = document.createElement('th'); th.textContent = value; th.style.padding = '8px'; header.appendChild(th);
    });
    table.querySelector('thead').replaceChildren(header);
    const rows = filtered.teachers.map(teacher => {
      const tr = document.createElement('tr'); tr.dataset.teacherId = teacher.id;
      const name = document.createElement('td'); name.textContent = teacher.name;
      const details = document.createElement('td');
      const subjectNames = catalog.subjects.filter(row => teacher.subjectIds.has(String(row.id))).map(row => ru ? (row.name_ru || row.name_kz) : (row.name_kz || row.name_ru));
      const classNames = catalog.classes.filter(row => teacher.classIds.has(String(row.id))).map(row => row.name);
      details.textContent = subjectNames.join(', ') + ' · ' + classNames.join(', ');
      tr.append(name, details);
      columns.forEach(([key, title]) => {
        const td = document.createElement('td');
        const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
        checkbox.name = key === 'teacher_ids' ? key : 'report_teacher_ids_' + key;
        checkbox.value = teacher.id; checkbox.checked = draft[key].has(teacher.id); checkbox.style.width = 'auto';
        checkbox.dataset.matrixFlag = key; checkbox.dataset.teacherId = teacher.id; checkbox.dataset.teacherName = teacher.name;
        checkbox.setAttribute('aria-label', teacher.name + ': ' + title); td.appendChild(checkbox); tr.appendChild(td);
      });
      Array.from(tr.children).forEach(cell => {cell.style.padding = '8px'; cell.style.borderBottom = '1px solid #dbe3ef';});
      return tr;
    });
    table.querySelector('tbody').replaceChildren(...rows);
    host.querySelector('[data-matrix-hint]').textContent = !input.subjects.length
      ? (ru ? 'Сначала выберите предмет проверки.' : 'Алдымен тексерілетін пәнді таңдаңыз.')
      : rows.length ? (ru ? 'Отметьте учителей по нужным отчётам. Исполнителей назначают на следующем шаге.' : 'Мұғалімдерді қажетті есептер бойынша белгілеңіз. Орындаушылар келесі қадамда тағайындалады.')
      : (ru ? 'В выбранных классах нет активной нагрузки по выбранному предмету. Проверьте учебную нагрузку школы.' : 'Таңдалған сыныптарда осы пән бойынша белсенді жүктеме жоқ. Мектептің оқу жүктемесін тексеріңіз.');
    root.querySelector('#report-teacher-targets').hidden = scope === 'documentation';
    window.ReportAreaEditor?.refresh(root, controlFlow, filtered, input);
  }

  function filterReportsByCurrentSelection(root, scopeCode, reports) {
    const READING_SPEED_CODE = "reading_speed_table";

    let filtered = Array.isArray(reports) ? [...reports] : [];

    if (scopeCode === "class") {
      const selectedGroups = getCheckedValues(
        root,
        '#scope-detail-container input[name="class_groups"]:checked'
      );

      const hasPrimary = selectedGroups.includes("1_4");

      filtered = filtered.filter((report) => {
        if (String(report.code) !== READING_SPEED_CODE) {
          return true;
        }

        return hasPrimary;
      });
    }

    if (scopeCode === "parallel") {
      const selectedParallels = getCheckedValues(
        root,
        '#scope-detail-container input[name="parallel_classes"]:checked'
      );

      const hasPrimary = selectedParallels.some((v) =>
        ["1", "2", "3", "4"].includes(String(v))
      );

      filtered = filtered.filter((report) => {
        if (String(report.code) !== READING_SPEED_CODE) {
          return true;
        }

        return hasPrimary;
      });
    }

    return filtered;
  }

  function buildGeneratedMaterials(root, controlFlow) {
    const catalog = controlFlow.algorithm_catalog;
    if (!catalog) return [];
    const lang = root.querySelector('[data-algorithm-matrix]')?.dataset.language === 'ru' ? 'ru' : 'kk';
    const scope = root.querySelector('#control_scope')?.value || '';
    const reports = getCheckedItems(root, 'input[name="report_types"]');
    const classes = getCheckedValues(root, 'input[name="school_class_ids"]');
    const subjects = getCheckedValues(root, 'input[name="subjects"]');
    const parallels = getCheckedValues(root, 'input[name="parallel_classes"]');
    const teachers = new Map(catalog.teaching.map(row => [String(row.teacher_id), row.full_name]));
    const label = (kind, value) => kind === 'teacher' ? teachers.get(String(value)) || value
      : kind === 'class' ? catalog.classes.find(row => String(row.id) === String(value))?.name || value
      : kind === 'subject' ? (catalog.subjects.find(row => String(row.id) === String(value))?.[lang === 'ru' ? 'name_ru' : 'name_kz'] || catalog.subjects.find(row => String(row.id) === String(value))?.[lang === 'ru' ? 'name_kz' : 'name_ru'] || value) : value;
    const selectedClasses = algorithmView(catalog,{scope,subjects,parallels,groups:getCheckedValues(root,'input[name="class_groups"]'),classIds:classes}).selected;
    const subjectPairs = catalog.subject_classes || catalog.teaching;
    const generated = [];
    reports.forEach(report => {
      const areaState = window.ReportAreaEditor?.data(root);
      if (areaState?.enabled && ['knowledge_quality_table','class_summary'].includes(report.value)) {
        areaState.areas.filter(a => a.report_codes.includes(report.value)).forEach(a => {
          const names = catalog.subjects.map(s => {
            const ids = new Set(a.pairs.filter(p => p.subject_id === s.id).map(p => p.class_id));
            return ids.size ? (lang === 'ru' ? s.name_ru || s.name_kz : s.name_kz || s.name_ru) + ': ' + catalog.classes.filter(c => ids.has(c.id)).map(c => c.name).join(', ') : '';
          }).filter(Boolean);
          generated.push({report_type:report.value, report_label:controlFlow.report_labels?.[report.value]?.[lang] || executionLabel(report.label),
            target_kind:'report_area', target_value:a.id, target_label:(lang === 'ru' ? a.name_ru || a.name_kk : a.name_kk || a.name_ru) || (lang === 'ru' ? 'Без названия' : 'Атаусыз'), context_label:names.join('; '), order:generated.length+1,scope});
        });
        return;
      }
      let kind, values;
      if (report.value === 'analytical_reference') {kind = 'documentation'; values = ['Итоговая справка / Қорытынды анықтама'];}
      else if (['lesson_observation', 'checking_notebooks_table'].includes(report.value)) {
        kind = 'teacher'; values = getCheckedValues(root, 'input[name="report_teacher_ids_' + report.value + '"]');
      } else if (report.value === 'teacher_analysis' || scope === 'teacher') {kind = 'teacher'; values = getCheckedValues(root, 'input[name="teacher_ids"]');}
      else if (report.value === 'reading_speed_table' && !['class', 'parallel'].includes(scope)) {kind = 'class'; values = algorithmView(catalog, {scope, subjects, parallels, groups: getCheckedValues(root, 'input[name="class_groups"]'), classIds: classes}).selected.map(row => String(row.id));}
      else if (report.value === 'document_analysis' || scope === 'documentation') {kind = 'documentation'; values = ['Документы задачи / Тапсырма құжаттары'];}
      else if (scope === 'parallel') {kind = 'parallel_class'; values = parallels;}
      else if (scope === 'class') {kind = 'class'; values = classes;}
      else {kind = 'subject'; values = subjects;}
      Array.from(new Set(values)).forEach(value => generated.push({report_type: report.value, report_label: controlFlow.report_labels?.[report.value]?.[lang] || executionLabel(report.label),
        target_kind: kind, target_value: String(value), target_label: label(kind, value),
        context_label: kind === 'subject' ? selectedClasses.filter(c => subjectPairs.some(p => String(p.subject_id) === String(value) && String(p.class_id) === String(c.id))).map(c => c.name).join(', ') : '',
        teacher_id: kind === 'teacher' ? String(value) : null, teacher_name: kind === 'teacher' ? label(kind, value) : null,
        order: generated.length + 1, scope}));
    });
    return generated;
  }

  function renderGeneratedMaterials(root, generated) {
    const summary = root.querySelector('#materials-preview-summary'), list = root.querySelector('#materials-preview-list'), hidden = root.querySelector('#generated_reports_json');
    if (!summary || !list || !hidden) return;
    summary.textContent = (root.querySelector('[data-algorithm-matrix]')?.dataset.language === 'ru' ? 'Материалов к подготовке: ' : 'Дайындалатын материалдар: ') + generated.length;
    const rows = generated.map(item => {
      const li = document.createElement('li'); li.textContent = item.order + '. ' + executionLabel(item.report_label) + ' — ' + item.target_label + (item.context_label ? ' · ' + item.context_label : ''); return li;
    });
    list.replaceChildren(...rows); hidden.value = JSON.stringify(generated);
  }

  function updateReviewResultField(root) {
    const inputEl =
      root.querySelector("#review_result") ||
      document.querySelector("#review_result");

    const hiddenEl =
      root.querySelector("#generated_reports_json") ||
      document.querySelector("#generated_reports_json");

    if (!hiddenEl) {
      console.warn("generated_reports_json not found");
      return;
    }

    if (!inputEl) {
      console.warn("review_result not found");
      return;
    }

    let data = [];

    try {
      data = JSON.parse(hiddenEl.value || "[]");
    } catch (e) {
      console.warn("generated_reports_json parse error", e);
      return;
    }

    if (!data.length) {
      inputEl.value = "";
      return;
    }

    const uniqueLabels = [
      ...new Set(data.map((item) => item.report_label).filter(Boolean)),
    ];

    inputEl.value = uniqueLabels.join(", ");
  }

  function updateGeneratedMaterialsPreview(root, controlFlow) {
    const generated = buildGeneratedMaterials(root, controlFlow);
    renderGeneratedMaterials(root, generated);
    updateReviewResultField(root);
  }

  function bindGeneratedMaterialsPreview(root, controlFlow) {
    const refresh = () => updateGeneratedMaterialsPreview(root, controlFlow);

    root.addEventListener("change", (event) => {
      const el = event.target;

      if (!el) return;

      const matchers = [
        '#scope-detail-container input[type="checkbox"]',
        '#scope-detail-container select',
        '#teacher-detail-container input[type="checkbox"]',
        '#teacher-detail-container select',
        '#report_type input[type="checkbox"]',
        "#control_scope",
        "#control_form",
        "#control_kind",
      ];

      if (matchers.some((selector) => el.matches(selector))) {
        setTimeout(refresh, 0);
      }
    });

    refresh();
  }

  function initTaskExecuteForm(root) {
    if (!root) return;

    const formRoot = root.querySelector("#system-reports-execute-form");

    if (!formRoot) {
      return;
    }

    const dataEl = formRoot.querySelector("#task-execution-json-data");

    if (!dataEl) {
      console.debug("task-execution-json-data not ready yet");
      return;
    }

    if (formRoot.dataset.initialized === "1") {
      return;
    }

    formRoot.dataset.initialized = "1";

    const controlFlow = safeJsonParse(dataEl.dataset.controlFlow, {});
    const state = safeJsonParse(dataEl.dataset.state, {});
    const catalog = controlFlow.algorithm_catalog;
    const ruMatrix = formRoot.querySelector('[data-algorithm-matrix]')?.dataset.language === 'ru';
    const subjectOptions = catalog.subjects.map(row => ({code: String(row.id), label: ruMatrix ? (row.name_ru || row.name_kz) : (row.name_kz || row.name_ru)}));
    const availableGrades = new Set(catalog.classes.map(row => String(row.grade_level)));
    controlFlow.details_by_scope.parallel.options = (controlFlow.details_by_scope.parallel.options || []).filter(row => availableGrades.has(String(row.code)));

    ['subject', 'teacher', 'complex'].forEach(key => {if (controlFlow.details_by_scope[key]) controlFlow.details_by_scope[key].options = subjectOptions;});
    state.subjects = (state.subjects || []).map(value => {
      const row = catalog.subjects.find(item => [String(item.id), item.name_ru, item.name_kz].includes(String(value)));
      return row ? String(row.id) : String(value);
    });


    const savedScope = state.control_scope || "";
    const savedForm = state.control_form || "";
    const savedKind = state.control_kind || "";

    const savedReportRaw = state.report_types || state.report_type || [];
    const savedReports = Array.isArray(savedReportRaw)
      ? savedReportRaw
      : savedReportRaw
        ? [savedReportRaw]
        : [];

    const savedSubjectsRaw = state.subjects || [];
    const savedSubjects = Array.isArray(savedSubjectsRaw)
      ? savedSubjectsRaw
      : savedSubjectsRaw
        ? [savedSubjectsRaw]
        : [];

    const savedClassGroupsRaw = state.class_groups || [];
    const savedClassGroups = Array.isArray(savedClassGroupsRaw)
      ? savedClassGroupsRaw
      : savedClassGroupsRaw
        ? [savedClassGroupsRaw]
        : [];

    const savedParallelClassesRaw = state.parallel_classes || [];
    const savedParallelClasses = Array.isArray(savedParallelClassesRaw)
      ? savedParallelClassesRaw
      : savedParallelClassesRaw
        ? [savedParallelClassesRaw]
        : [];

    const savedTeacherIdsRaw = state.teacher_ids || [];
    const savedTeacherIds = Array.isArray(savedTeacherIdsRaw)
      ? savedTeacherIdsRaw
      : savedTeacherIdsRaw
        ? [savedTeacherIdsRaw]
        : [];

    const savedTeacherId = state.teacher_id || "";

    const scopeEl = formRoot.querySelector("#control_scope");
    const formEl = formRoot.querySelector("#control_form");
    const kindEl = formRoot.querySelector("#control_kind");
    const reportEl = formRoot.querySelector("#report_type");
    const hintEl = formRoot.querySelector("#control_hint");

    const detailWrapperEl = formRoot.querySelector("#scope-detail-wrapper");
    const detailLabelEl = formRoot.querySelector("#scope-detail-label");
    const detailContainerEl = formRoot.querySelector("#scope-detail-container");

    const teacherWrapperEl = formRoot.querySelector("#teacher-detail-wrapper");
    const teacherLabelEl = formRoot.querySelector("#teacher-detail-label");
    const teacherContainerEl = formRoot.querySelector("#teacher-detail-container");

    if (
      !scopeEl ||
      !formEl ||
      !kindEl ||
      !reportEl ||
      !hintEl ||
      !detailWrapperEl ||
      !detailLabelEl ||
      !detailContainerEl ||
      !teacherWrapperEl ||
      !teacherLabelEl ||
      !teacherContainerEl
    ) {
      return;
    }

    function resetReportCheckboxes(message = window.SchoolMonitorI18n.t("tx_056688a73c8b")) {
      reportEl.innerHTML = `<div class="checkbox-placeholder">${message}</div>`;
    }

    function fillReportCheckboxes(items, selectedValues = []) {
      reportEl.innerHTML = "";

      if (!items || !items.length) {
        resetReportCheckboxes(window.SchoolMonitorI18n.t("tx_e71c63f6a181"));
        return;
      }

      const normalizedSelected = selectedValues.map(String);

      items.forEach((item) => {
        const wrapper = document.createElement("div");
        wrapper.className = "checkbox-item";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.name = "report_types";
        input.value = item.code;
        input.id = `report_${String(item.code).replace(/[^a-zA-Z0-9_-]/g, "_")}`;
        input.checked = normalizedSelected.includes(String(item.code));
        const localizedReport = controlFlow.report_labels?.[item.code]?.[ruMatrix ? 'ru' : 'kk'] || executionLabel(item.label) || item.code;
        input.dataset.label = localizedReport;

        const label = document.createElement("label");
        label.setAttribute("for", input.id);
        label.textContent = localizedReport;

        wrapper.appendChild(input);
        wrapper.appendChild(label);
        reportEl.appendChild(wrapper);
      });
    }

    function clearScopeDetails() {
      detailContainerEl.innerHTML = "";
      detailWrapperEl.style.display = "none";
    }

    function clearTeacherDetails() {
      teacherContainerEl.innerHTML = "";
      teacherWrapperEl.style.display = "none";
    }

    function getCheckedValuesByName(name) {
      return Array.from(
        formRoot.querySelectorAll(`input[name="${name}"]:checked`)
      ).map((el) => el.value);
    }

    function mergeReports(...groups) {
      const result = [];
      const seen = new Set();

      groups.flat().forEach((report) => {
        if (!report || !report.code) return;

        const code = String(report.code);

        if (seen.has(code)) return;

        seen.add(code);
        result.push(report);
      });

      return result;
    }

    function getReportsForCurrentSelection(scopeCode) {
      const reportsConfig = controlFlow.reports_by_scope?.[scopeCode];

      if (!scopeCode || !reportsConfig) {
        return [];
      }

      if (Array.isArray(reportsConfig)) {
        return reportsConfig;
      }

      if (scopeCode === "class") {
        const selectedGroups = getCheckedValuesByName("class_groups");

        const hasPrimary = selectedGroups.includes("1_4");
        const hasMiddle = selectedGroups.includes("5_9");
        const hasHigh = selectedGroups.includes("10_11");

        const reportGroups = [];

        if (hasPrimary) {
          reportGroups.push(reportsConfig["1_4"] || []);
        }

        if (hasMiddle) {
          reportGroups.push(reportsConfig["5_9"] || []);
        }

        if (hasHigh) {
          reportGroups.push(reportsConfig["10_11"] || []);
        }

        if (reportGroups.length) {
          return mergeReports(...reportGroups);
        }

        return reportsConfig.default || [];
      }

      if (scopeCode === "parallel") {
        const selectedParallels = getCheckedValuesByName("parallel_classes");

        const hasPrimary = selectedParallels.some((v) =>
          ["1", "2", "3", "4"].includes(String(v))
        );

        const hasSubject = selectedParallels.some((v) =>
          ["5", "6", "7", "8", "9", "10", "11"].includes(String(v))
        );

        const reportGroups = [];

        if (hasPrimary) {
          reportGroups.push(reportsConfig.primary || []);
        }

        if (hasSubject) {
          reportGroups.push(reportsConfig.subject || []);
        }

        if (reportGroups.length) {
          return mergeReports(...reportGroups);
        }

        return reportsConfig.default || [];
      }

      return reportsConfig.default || [];
    }

    function getScopeLabel(scopeCode) {
      return (
        (controlFlow.scopes || []).find(
          (x) => String(x.code) === String(scopeCode)
        )?.label || ""
      );
    }

    function getFormLabel(scopeCode, formCode) {
      return (
        (controlFlow.forms_by_scope?.[scopeCode] || []).find(
          (x) => String(x.code) === String(formCode)
        )?.label || ""
      );
    }

    function getKindLabel(kindCode) {
      return (
        (controlFlow.kinds || []).find(
          (x) => String(x.code) === String(kindCode)
        )?.label || ""
      );
    }

    function getReportLabels(scopeCode) {
      const checkedValues = Array.from(
        reportEl.querySelectorAll('input[name="report_types"]:checked')
      ).map((el) => el.value);

      const reports = getReportsForCurrentSelection(scopeCode);

      return reports
        .filter((x) => checkedValues.includes(String(x.code)))
        .map((x) => x.label);
    }

    function getSelectedTeacherLabels() {
      const checkedTeacherIds = getCheckedValuesByName("teacher_ids");

      if (!checkedTeacherIds.length) return [];

      const allTeachers = [
        ...(controlFlow.primary_teachers || []),
        ...Object.values(controlFlow.teachers_by_subject || {}).flat(),
        ...(controlFlow.teachers || []),
      ];

      const uniq = new Map();

      allTeachers.forEach((teacher) => {
        uniq.set(String(teacher.code), teacher.label);
      });

      return checkedTeacherIds
        .map((id) => uniq.get(String(id)))
        .filter(Boolean);
    }

    function buildScopeOptions() {
      fillSelect(scopeEl, controlFlow.scopes || [], savedScope, window.SchoolMonitorI18n.t("tx_6a323db2ae5b"));
    }

    function buildFormOptions(selectedForm = "") {
      const scopeCode = scopeEl.value;
      const forms = controlFlow.forms_by_scope?.[scopeCode] || [];

      if (!scopeCode || !forms.length) {
        resetSelect(formEl, window.SchoolMonitorI18n.t("tx_056688a73c8b"), true);
        hintEl.textContent =
          window.SchoolMonitorI18n.t("tx_afb59fac949e");
        return;
      }

      fillSelect(formEl, forms, selectedForm, window.SchoolMonitorI18n.t("tx_d4fea40dd0de"));
    }

    function buildKindOptions(selectedKind = "") {
      const scopeCode = scopeEl.value;

      if (!scopeCode) {
        resetSelect(kindEl, window.SchoolMonitorI18n.t("tx_056688a73c8b"), true);
        return;
      }

      fillSelect(kindEl, controlFlow.kinds || [], selectedKind, window.SchoolMonitorI18n.t("tx_a28f806a209d"));
    }

    function buildReportOptions(selectedReports = []) {
      const scopeCode = scopeEl.value;

      let reports = getReportsForCurrentSelection(scopeCode);

      if (!scopeCode || !reports.length) {
        resetReportCheckboxes(window.SchoolMonitorI18n.t("tx_056688a73c8b"));
        return;
      }

      reports = filterReportsByCurrentSelection(formRoot, scopeCode, reports);

      if (!reports.length) {
        resetReportCheckboxes(window.SchoolMonitorI18n.t("tx_e71c63f6a181"));
        return;
      }

      fillReportCheckboxes(reports, selectedReports);
    }

    function renderSubjectExtraBlock(containerId) {
      const oldBlock = detailContainerEl.querySelector(`#${containerId}`)?.closest(".subject-extra-block");

      if (oldBlock) {
        oldBlock.remove();
      }

      const subjectBlock = document.createElement("div");
      subjectBlock.className = "subject-extra-block";
      subjectBlock.style.marginTop = "16px";

      const subjectTitle = document.createElement("div");
      subjectTitle.className = "form-label";
      subjectTitle.textContent = window.SchoolMonitorI18n.t("tx_854f5a732eab");

      const subjectContainer = document.createElement("div");
      subjectContainer.id = containerId;

      subjectBlock.appendChild(subjectTitle);
      subjectBlock.appendChild(subjectContainer);

      detailContainerEl.appendChild(subjectBlock);

      renderCheckboxGroup(
        subjectContainer,
        "subjects",
        controlFlow.details_by_scope?.subject?.options || [],
        savedSubjects
      );
    }

    function updateTeacherOptions() {
      clearTeacherDetails();
      teacherWrapperEl.hidden = true;
      teacherWrapperEl.style.display = 'none';
    }

    function buildDetailOptions() {
      clearScopeDetails();
      clearTeacherDetails();

      const scopeCode = scopeEl.value;
      const detailConfig = controlFlow.details_by_scope?.[scopeCode];

      if (!scopeCode || !detailConfig) {
        return;
      }

      detailWrapperEl.style.display = "block";
      detailLabelEl.textContent =
        executionLabel(detailConfig.label) || window.SchoolMonitorI18n.t("tx_6f97e823e641");

      if (detailConfig.type === "checkbox") {
        let selectedValues = [];

        if (detailConfig.name === "class_groups") {
          selectedValues = savedClassGroups;
        } else if (detailConfig.name === "parallel_classes") {
          selectedValues = savedParallelClasses;
        } else if (detailConfig.name === "subjects") {
          selectedValues = savedSubjects;
        } else if (detailConfig.name === "teacher_ids") {
          selectedValues = savedTeacherIds;
        }

        renderCheckboxGroup(
          detailContainerEl,
          detailConfig.name,
          detailConfig.options || [],
          selectedValues
        );

        if (scopeCode === "class") {
          const hasSubjectGroups =
            selectedValues.includes("5_9") ||
            selectedValues.includes("10_11");

          if (hasSubjectGroups) {
            renderSubjectExtraBlock("class-subjects-container");
          }
        }

        if (scopeCode === "parallel") {
          const hasSubjectParallels = selectedValues.some((v) =>
            ["5", "6", "7", "8", "9", "10", "11"].includes(String(v))
          );

          if (hasSubjectParallels) {
            renderSubjectExtraBlock("parallel-subjects-container");
          }
        }
      } else if (detailConfig.type === "select") {
        renderSingleSelect(
          detailContainerEl,
          detailConfig.name,
          detailConfig.options || [],
          savedTeacherId
        );
      } else if (detailConfig.type === "info") {
        detailContainerEl.innerHTML =
          window.SchoolMonitorI18n.t("tx_d2daaffcc7cb");
      }

      updateTeacherOptions(scopeCode, detailConfig, true);
    }

    function rebuildDynamicSubjectBlockIfNeeded() {
      const scopeCode = scopeEl.value;
      const detailConfig = controlFlow.details_by_scope?.[scopeCode];

      if (!scopeCode || !detailConfig) return;

      if (scopeCode === "class") {
        const selectedGroups = getCheckedValuesByName("class_groups");
        const hasSubjectGroups = selectedGroups.length > 0;

        const existingBlock = detailContainerEl.querySelector("#class-subjects-container")
          ?.closest(".subject-extra-block");

        if (hasSubjectGroups && !existingBlock) {
          renderSubjectExtraBlock("class-subjects-container");
        }

        if (!hasSubjectGroups && existingBlock) {
          existingBlock.remove();
        }
      }

      if (scopeCode === "parallel") {
        const selectedParallels = getCheckedValuesByName("parallel_classes");
        const hasSubjectParallels = selectedParallels.length > 0;

        const existingBlock = detailContainerEl.querySelector("#parallel-subjects-container")
          ?.closest(".subject-extra-block");

        if (hasSubjectParallels && !existingBlock) {
          renderSubjectExtraBlock("parallel-subjects-container");
        }

        if (!hasSubjectParallels && existingBlock) {
          existingBlock.remove();
        }
      }
    }

    function updateHint() {
      const scopeCode = scopeEl.value;
      const formCode = formEl.value;
      const kindCode = kindEl.value;

      if (!scopeCode) {
        hintEl.textContent =
          window.SchoolMonitorI18n.t("tx_afb59fac949e");
        return;
      }

      const scopeLabel = executionLabel(getScopeLabel(scopeCode));
      const formLabel = formCode ? executionLabel(getFormLabel(scopeCode, formCode)) : "";
      const kindLabel = kindCode ? executionLabel(getKindLabel(kindCode)) : "";
      const reportLabels = getReportLabels(scopeCode).map(executionLabel);
      const teacherLabels = getSelectedTeacherLabels();

      let detailLabels = [];
      const detailConfig = controlFlow.details_by_scope?.[scopeCode];

      if (detailConfig?.type === "checkbox") {
        const selectedCodes = getCheckedValuesByName(detailConfig.name);
        const detailOptions = detailConfig.options || [];

        detailLabels = detailOptions
          .filter((item) => selectedCodes.includes(String(item.code)))
          .map((item) => item.label);

        const selectedSubjects = getCheckedValuesByName("subjects");
        const subjectOptions = controlFlow.details_by_scope?.subject?.options || [];

        const subjectLabels = subjectOptions
          .filter((item) => selectedSubjects.includes(String(item.code)))
          .map((item) => item.label);

        if (
          (scopeCode === "class" || scopeCode === "parallel") &&
          subjectLabels.length
        ) {
          detailLabels.push(subjectLabels.join(", "));
        }
      } else if (detailConfig?.type === "select") {
        const selectEl = detailContainerEl.querySelector(
          `select[name="${detailConfig.name}"]`
        );

        if (selectEl && selectEl.value) {
          const option = selectEl.options[selectEl.selectedIndex];

          if (option) {
            detailLabels = [option.textContent];
          }
        }
      }

      detailLabels = detailLabels.map(executionLabel);
      const parts = [scopeLabel];

      if (detailLabels.length) parts.push(detailLabels.join(", "));
      if (formLabel) parts.push(formLabel);
      if (kindLabel) parts.push(kindLabel);
      if (reportLabels.length) parts.push(reportLabels.join(", "));
      if (teacherLabels.length) parts.push(teacherLabels.join(", "));

      hintEl.textContent = window.SchoolMonitorI18n.t("tx_a767eb85b546") + parts.join(" → ");
    }

    function refreshAfterDetailChange() {
      const scopeCode = scopeEl.value;
      const detailConfig = controlFlow.details_by_scope?.[scopeCode];

      rebuildDynamicSubjectBlockIfNeeded();
      updateTeacherOptions(scopeCode, detailConfig, false);
      buildReportOptions(getCheckedValuesByName("report_types"));
      refreshAlgorithmMatrix(formRoot, controlFlow);
      updateHint();
      updateGeneratedMaterialsPreview(formRoot, controlFlow);
    }

    formRoot.addEventListener('change', (event) => {
      const target = event.target;
      if (!target) return;
      if (target.dataset.matrixFlag) {
        const values = formRoot._algorithmMatrix[target.dataset.matrixFlag];
        target.checked ? values.add(target.value) : values.delete(target.value);
        updateGeneratedMaterialsPreview(formRoot, controlFlow);
      } else if (target.dataset.algorithmClassId) {
        const values = formRoot._algorithmMatrix.classIds;
        target.checked ? values.add(target.value) : values.delete(target.value);
        refreshAlgorithmMatrix(formRoot, controlFlow); updateGeneratedMaterialsPreview(formRoot, controlFlow);
      } else if (target.matches('input[name="subjects"], input[name="report_types"], #control_scope, input[name="class_groups"], input[name="parallel_classes"]')) {
        refreshAlgorithmMatrix(formRoot, controlFlow); updateGeneratedMaterialsPreview(formRoot, controlFlow);
      }
    });

    scopeEl.addEventListener("change", function () {
      buildFormOptions();
      buildKindOptions();
      buildDetailOptions();
      buildReportOptions([]);
      updateHint();
      updateGeneratedMaterialsPreview(formRoot, controlFlow);
    });

    formEl.addEventListener("change", function () {
      updateHint();
      updateGeneratedMaterialsPreview(formRoot, controlFlow);
    });

    kindEl.addEventListener("change", function () {
      updateHint();
      updateGeneratedMaterialsPreview(formRoot, controlFlow);
    });

    reportEl.addEventListener("change", function (event) {
      if (event.target && event.target.matches('input[name="report_types"]')) {
        updateHint();
        updateGeneratedMaterialsPreview(formRoot, controlFlow);
      }
    });

    teacherContainerEl.addEventListener("change", function (event) {
      if (
        event.target &&
        (
          event.target.matches('input[name="teacher_ids"]') ||
          event.target.matches('select[name="teacher_id"]')
        )
      ) {
        updateHint();
        updateGeneratedMaterialsPreview(formRoot, controlFlow);
      }
    });

    detailContainerEl.addEventListener("change", function (event) {
      if (
        event.target &&
        (
          event.target.matches('input[name="class_groups"]') ||
          event.target.matches('input[name="parallel_classes"]') ||
          event.target.matches('input[name="subjects"]') ||
          event.target.matches('select[name="teacher_id"]')
        )
      ) {
        refreshAfterDetailChange();
      }
    });

    buildScopeOptions();

    if (savedScope) {
      buildFormOptions(savedForm);
      buildKindOptions(savedKind);
      buildDetailOptions();
      buildReportOptions(savedReports);
      updateHint();
    } else {
      resetSelect(formEl, window.SchoolMonitorI18n.t("tx_056688a73c8b"), true);
      resetSelect(kindEl, window.SchoolMonitorI18n.t("tx_056688a73c8b"), true);
      resetReportCheckboxes(window.SchoolMonitorI18n.t("tx_056688a73c8b"));
      clearScopeDetails();
      clearTeacherDetails();
    }

    refreshAlgorithmMatrix(formRoot, controlFlow);
    bindGeneratedMaterialsPreview(formRoot, controlFlow);

    setTimeout(() => {
      refreshAlgorithmMatrix(formRoot, controlFlow);
      updateGeneratedMaterialsPreview(formRoot, controlFlow);
    }, 50);
  }

  function autoLoadAcceptedTask() {
    const select = document.getElementById("selected_task_id");

    if (!select || !select.value) return;

    if (select.dataset.autoloaded === "1") return;

    select.dataset.autoloaded = "1";

    if (window.htmx) {
      window.htmx.trigger(select, "change");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    autoLoadAcceptedTask();

    const existingRoot = document.querySelector("#task-execution-details");
    if (existingRoot) {
      initTaskExecuteForm(existingRoot);
    }
  });

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.target && event.target.id === "task-execution-details") {
      initTaskExecuteForm(event.target);
    }
  });

  window.initTaskExecuteForm = initTaskExecuteForm;
  window.updateReviewResultField = updateReviewResultField;
  window.updateGeneratedMaterialsPreview = updateGeneratedMaterialsPreview;
})();