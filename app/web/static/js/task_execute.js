(function () {
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
      option.textContent = item.label;

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
        '<div class="checkbox-placeholder">Нет данных для выбора</div>';
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
      label.textContent = item.label || item.code;

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
    defaultOption.textContent = "Выберите";
    select.appendChild(defaultOption);

    (items || []).forEach((item) => {
      const option = document.createElement("option");
      option.value = item.code;
      option.textContent = item.label;

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

  function getTeacherPoolBySelectedSubjects(controlFlow, selectedSubjects) {
    const teachersMap = controlFlow.teachers_by_subject || {};
    let teachers = [];

    selectedSubjects.forEach((subjectCode) => {
      const subjectTeachers = teachersMap[subjectCode] || [];

      subjectTeachers.forEach((teacher) => {
        teachers.push({
          code: String(teacher.code),
          label: teacher.label || String(teacher.code),
          subject_code: subjectCode,
        });
      });
    });

    return uniqueBy(teachers, (x) => String(x.code));
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
    const scope = root.querySelector("#control_scope")?.value || "";

    const selectedReports = getCheckedItems(
      root,
      '#report_type input[type="checkbox"][name="report_types"]'
    );

    const selectedTeacherItems = getCheckedItems(
      root,
      '#teacher-detail-container input[type="checkbox"][name="teacher_ids"]'
    );

    const selectedSubjects = getCheckedValues(
      root,
      '#scope-detail-container input[type="checkbox"][name="subjects"]'
    );

    const selectedClassGroups = getCheckedValues(
      root,
      '#scope-detail-container input[type="checkbox"][name="class_groups"]'
    );

    const selectedParallelClasses = getCheckedValues(
      root,
      '#scope-detail-container input[type="checkbox"][name="parallel_classes"]'
    );

    const generated = [];

    const REFERENCE_CODE = "analytical_reference";
    const KNOWLEDGE_QUALITY_CODE = "knowledge_quality_table";
    const LESSON_OBSERVATION_CODE = "lesson_observation";
    const CHECKING_NOTEBOOKS_CODE = "checking_notebooks_table";
    const READING_SPEED_CODE = "reading_speed_table";

    const referenceReport = selectedReports.find(
      (r) => String(r.value) === REFERENCE_CODE
    );

    const otherReports = selectedReports.filter(
      (r) => String(r.value) !== REFERENCE_CODE
    );

    if (referenceReport) {
      generated.push({
        report_type: referenceReport.value,
        report_label: referenceReport.label,
        order: generated.length + 1,
        is_common: true,
        scope,
        subject_codes: selectedSubjects,
        class_groups: selectedClassGroups,
        parallel_classes: selectedParallelClasses,
      });
    }

    function pushPerSelectedTeachers(reports, teachers, extra = {}) {
      if (!teachers.length) return;

      teachers.forEach((teacher) => {
        reports.forEach((report) => {
          generated.push({
            teacher_id: String(teacher.value ?? teacher.code ?? teacher.id),
            teacher_name: teacher.label || teacher.teacher_name || "",
            report_type: report.value,
            report_label: report.label,
            order: generated.length + 1,
            scope,
            ...extra,
          });
        });
      });
    }

    if (scope === "teacher") {
      pushPerSelectedTeachers(otherReports, selectedTeacherItems, {
        subject_codes: selectedSubjects,
      });

      return generated;
    }

    if (scope === "subject") {
      const commonReports = [];
      const perTeacherReports = [];

      otherReports.forEach((report) => {
        if (String(report.value) === KNOWLEDGE_QUALITY_CODE) {
          commonReports.push(report);
        } else {
          perTeacherReports.push(report);
        }
      });

      commonReports.forEach((report) => {
        generated.push({
          report_type: report.value,
          report_label: report.label,
          order: generated.length + 1,
          is_common: true,
          scope,
          subject_codes: selectedSubjects,
        });
      });

      pushPerSelectedTeachers(perTeacherReports, selectedTeacherItems, {
        subject_codes: selectedSubjects,
      });

      return generated;
    }

    if (scope === "class" || scope === "parallel") {
      const perTeacherCodes = new Set([
        LESSON_OBSERVATION_CODE,
        CHECKING_NOTEBOOKS_CODE,
        READING_SPEED_CODE,
      ]);

      const commonReports = [];
      const perTeacherReports = [];

      otherReports.forEach((report) => {
        if (perTeacherCodes.has(String(report.value))) {
          perTeacherReports.push(report);
        } else {
          commonReports.push(report);
        }
      });

      commonReports.forEach((report) => {
        generated.push({
          report_type: report.value,
          report_label: report.label,
          order: generated.length + 1,
          is_common: true,
          scope,
          subject_codes: selectedSubjects,
          class_groups: selectedClassGroups,
          parallel_classes: selectedParallelClasses,
        });
      });

      pushPerSelectedTeachers(perTeacherReports, selectedTeacherItems, {
        subject_codes: selectedSubjects,
        class_groups: selectedClassGroups,
        parallel_classes: selectedParallelClasses,
      });

      return generated;
    }

    otherReports.forEach((report) => {
      generated.push({
        report_type: report.value,
        report_label: report.label,
        order: generated.length + 1,
        scope,
      });
    });

    return generated;
  }

  function renderGeneratedMaterials(root, generated) {
    const summaryEl = root.querySelector("#materials-preview-summary");
    const listEl = root.querySelector("#materials-preview-list");
    const hiddenEl = root.querySelector("#generated_reports_json");

    if (!summaryEl || !listEl || !hiddenEl) return;

    if (!generated.length) {
      summaryEl.textContent =
        "После выбора параметров здесь появится список материалов.";
      listEl.innerHTML = "";
      hiddenEl.value = "[]";
      return;
    }

    const counts = {};

    generated.forEach((item) => {
      counts[item.report_label] = (counts[item.report_label] || 0) + 1;
    });

    const summaryParts = Object.entries(counts).map(
      ([label, count]) => `${count} × ${label}`
    );

    summaryEl.textContent = `Будет подготовлено: ${summaryParts.join(", ")}`;

    listEl.innerHTML = generated
      .map((item) => {
        if (item.teacher_name) {
          return `<li>${item.order}. ${item.report_label} — ${item.teacher_name}</li>`;
        }

        if (item.is_common) {
          return `<li>${item.order}. ${item.report_label} — общий материал</li>`;
        }

        return `<li>${item.order}. ${item.report_label}</li>`;
      })
      .join("");

    hiddenEl.value = JSON.stringify(generated);
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

    const formRoot = root.querySelector(".execute-form") || root;
    if (!formRoot) return;

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

    function resetReportCheckboxes(message = "Сначала выберите объект") {
      reportEl.innerHTML = `<div class="checkbox-placeholder">${message}</div>`;
    }

    function fillReportCheckboxes(items, selectedValues = []) {
      reportEl.innerHTML = "";

      if (!items || !items.length) {
        resetReportCheckboxes("Нет доступных типов отчета");
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
        input.dataset.label = item.label || item.code;

        const label = document.createElement("label");
        label.setAttribute("for", input.id);
        label.textContent = item.label || item.code;

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
      fillSelect(scopeEl, controlFlow.scopes || [], savedScope, "Выберите");
    }

    function buildFormOptions(selectedForm = "") {
      const scopeCode = scopeEl.value;
      const forms = controlFlow.forms_by_scope?.[scopeCode] || [];

      if (!scopeCode || !forms.length) {
        resetSelect(formEl, "Сначала выберите объект", true);
        hintEl.textContent =
          "Сначала выберите объект контроля. После этого система предложит допустимые формы, виды и типы отчета.";
        return;
      }

      fillSelect(formEl, forms, selectedForm, "Выберите форму");
    }

    function buildKindOptions(selectedKind = "") {
      const scopeCode = scopeEl.value;

      if (!scopeCode) {
        resetSelect(kindEl, "Сначала выберите объект", true);
        return;
      }

      fillSelect(kindEl, controlFlow.kinds || [], selectedKind, "Выберите вид");
    }

    function buildReportOptions(selectedReports = []) {
      const scopeCode = scopeEl.value;

      let reports = getReportsForCurrentSelection(scopeCode);

      if (!scopeCode || !reports.length) {
        resetReportCheckboxes("Сначала выберите объект");
        return;
      }

      reports = filterReportsByCurrentSelection(formRoot, scopeCode, reports);

      if (!reports.length) {
        resetReportCheckboxes("Нет доступных типов отчета");
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
      subjectTitle.textContent = "Пәндер";

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

    function updateTeacherOptions(scopeCode, detailConfig, isInitial = false) {
      clearTeacherDetails();

      if (!scopeCode || !detailConfig) {
        return;
      }

      if (scopeCode === "subject" || scopeCode === "teacher") {
        const selectedSubjects = getCheckedValuesByName(detailConfig.name);

        if (!selectedSubjects.length) {
          return;
        }

        const teachers = getTeacherPoolBySelectedSubjects(
          controlFlow,
          selectedSubjects
        );

        if (!teachers.length) {
          teacherWrapperEl.style.display = "block";
          teacherLabelEl.textContent = "Пән мұғалімдері";
          teacherContainerEl.innerHTML =
            '<div class="checkbox-placeholder">Бұл пән бойынша мұғалім табылмады</div>';
          return;
        }

        teacherWrapperEl.style.display = "block";
        teacherLabelEl.textContent =
          scopeCode === "teacher" ? "Мұғалімдер" : "Пән мұғалімдері";

        renderCheckboxGroup(
          teacherContainerEl,
          "teacher_ids",
          teachers.map((teacher) => ({
            code: teacher.code,
            label: teacher.label,
          })),
          isInitial ? savedTeacherIds : getCheckedValuesByName("teacher_ids")
        );

        return;
      }

      if (scopeCode === "class") {
        const selectedGroups = getCheckedValuesByName("class_groups");

        const hasPrimary = selectedGroups.includes("1_4");
        const hasSubjectGroups =
          selectedGroups.includes("5_9") || selectedGroups.includes("10_11");

        let teachers = [];

        if (hasPrimary && !hasSubjectGroups) {
          teachers = teachers.concat(controlFlow.primary_teachers || []);
        }

        if (hasPrimary && hasSubjectGroups) {
          teachers = teachers.concat(controlFlow.primary_teachers || []);
        }

        if (hasSubjectGroups) {
          const selectedSubjects = getCheckedValuesByName("subjects");

          teacherWrapperEl.style.display = "block";
          teacherLabelEl.textContent = hasPrimary
            ? "Бастауыш және пән мұғалімдері"
            : "Пән мұғалімдері";

          if (!selectedSubjects.length) {
            teacherContainerEl.innerHTML =
              '<div class="checkbox-placeholder">Алдымен пәнді таңдаңыз</div>';
            return;
          }

          teachers = teachers.concat(
            getTeacherPoolBySelectedSubjects(controlFlow, selectedSubjects)
          );
        }

        teachers = uniqueBy(teachers, (x) => String(x.code));

        if (!teachers.length) {
          teacherWrapperEl.style.display = "block";
          teacherContainerEl.innerHTML =
            '<div class="checkbox-placeholder">Мұғалім табылмады</div>';
          return;
        }

        teacherWrapperEl.style.display = "block";
        teacherLabelEl.textContent = hasSubjectGroups
          ? hasPrimary
            ? "Бастауыш және пән мұғалімдері"
            : "Пән мұғалімдері"
          : "Бастауыш сынып мұғалімдері";

        renderCheckboxGroup(
          teacherContainerEl,
          "teacher_ids",
          teachers,
          isInitial ? savedTeacherIds : getCheckedValuesByName("teacher_ids")
        );

        return;
      }

      if (scopeCode === "parallel") {
        const selectedParallels = getCheckedValuesByName("parallel_classes");

        const hasPrimaryParallel = selectedParallels.some((v) =>
          ["1", "2", "3", "4"].includes(String(v))
        );

        const hasSubjectParallel = selectedParallels.some((v) =>
          ["5", "6", "7", "8", "9", "10", "11"].includes(String(v))
        );

        let teachers = [];

        if (hasPrimaryParallel) {
          teachers = teachers.concat(controlFlow.primary_teachers || []);
        }

        if (hasSubjectParallel) {
          const selectedSubjects = getCheckedValuesByName("subjects");

          teacherWrapperEl.style.display = "block";
          teacherLabelEl.textContent = hasPrimaryParallel
            ? "Бастауыш және пән мұғалімдері"
            : "Пән мұғалімдері";

          if (!selectedSubjects.length) {
            teacherContainerEl.innerHTML =
              '<div class="checkbox-placeholder">Алдымен пәнді таңдаңыз</div>';
            return;
          }

          teachers = teachers.concat(
            getTeacherPoolBySelectedSubjects(controlFlow, selectedSubjects)
          );
        }

        teachers = uniqueBy(teachers, (x) => String(x.code));

        if (!teachers.length) {
          teacherWrapperEl.style.display = "block";
          teacherContainerEl.innerHTML =
            '<div class="checkbox-placeholder">Мұғалім табылмады</div>';
          return;
        }

        teacherWrapperEl.style.display = "block";
        teacherLabelEl.textContent = hasSubjectParallel
          ? hasPrimaryParallel
            ? "Бастауыш және пән мұғалімдері"
            : "Пән мұғалімдері"
          : "Бастауыш сынып мұғалімдері";

        renderCheckboxGroup(
          teacherContainerEl,
          "teacher_ids",
          teachers,
          isInitial ? savedTeacherIds : getCheckedValuesByName("teacher_ids")
        );
      }
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
        detailConfig.label || "Дополнительные данные";

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
          '<div class="checkbox-placeholder">Құжаттар бойынша бақылау</div>';
      }

      updateTeacherOptions(scopeCode, detailConfig, true);
    }

    function rebuildDynamicSubjectBlockIfNeeded() {
      const scopeCode = scopeEl.value;
      const detailConfig = controlFlow.details_by_scope?.[scopeCode];

      if (!scopeCode || !detailConfig) return;

      if (scopeCode === "class") {
        const selectedGroups = getCheckedValuesByName("class_groups");
        const hasSubjectGroups =
          selectedGroups.includes("5_9") || selectedGroups.includes("10_11");

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
        const hasSubjectParallels = selectedParallels.some((v) =>
          ["5", "6", "7", "8", "9", "10", "11"].includes(String(v))
        );

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
          "Сначала выберите объект контроля. После этого система предложит допустимые формы, виды и типы отчета.";
        return;
      }

      const scopeLabel = getScopeLabel(scopeCode);
      const formLabel = formCode ? getFormLabel(scopeCode, formCode) : "";
      const kindLabel = kindCode ? getKindLabel(kindCode) : "";
      const reportLabels = getReportLabels(scopeCode);
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

      const parts = [scopeLabel];

      if (detailLabels.length) parts.push(detailLabels.join(", "));
      if (formLabel) parts.push(formLabel);
      if (kindLabel) parts.push(kindLabel);
      if (reportLabels.length) parts.push(reportLabels.join(", "));
      if (teacherLabels.length) parts.push(teacherLabels.join(", "));

      hintEl.textContent = "Выбрано: " + parts.join(" → ");
    }

    function refreshAfterDetailChange() {
      const scopeCode = scopeEl.value;
      const detailConfig = controlFlow.details_by_scope?.[scopeCode];

      rebuildDynamicSubjectBlockIfNeeded();
      updateTeacherOptions(scopeCode, detailConfig, false);
      buildReportOptions(getCheckedValuesByName("report_types"));
      updateHint();
      updateGeneratedMaterialsPreview(formRoot, controlFlow);
    }

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
      resetSelect(formEl, "Сначала выберите объект", true);
      resetSelect(kindEl, "Сначала выберите объект", true);
      resetReportCheckboxes("Сначала выберите объект");
      clearScopeDetails();
      clearTeacherDetails();
    }

    bindGeneratedMaterialsPreview(formRoot, controlFlow);

    setTimeout(() => {
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