// static/js/meta_modal.js
(function () {
  const MONTH_NAMES = window.MONTH_NAMES || {};
  const $ = (id) => document.getElementById(id);

  function openModal(id) {
    const m = $(id);
    if (!m) return console.error("openModal: not found", id);
    m.setAttribute("aria-hidden", "false");
    m.classList.add("is-open");
  }

  function closeModal(id) {
    const m = $(id);
    if (!m) return;
    m.setAttribute("aria-hidden", "true");
    m.classList.remove("is-open");
  }

  async function fetchJsonOrText(resp) {
    const ct = (resp.headers.get("content-type") || "").toLowerCase();
    if (ct.includes("application/json")) return await resp.json();
    return await resp.text();
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function renderPeriodHtml(type, monthInt, monthsCsv) {
    if (type === "all_year") return `<span class="badge">Жыл бойы</span>`;
    if (type === "monthly")  return `<span class="badge">Ай сайын</span>`;
    if (type === "quarter")  return `<span class="badge">Тоқсан сайын</span>`;

    if (type === "month") {
      const key = monthInt != null ? String(monthInt) : "";
      const t = key ? (MONTH_NAMES[key] || MONTH_NAMES[monthInt] || "-") : "-";
      return `<span class="badge">${escapeHtml(t)}</span>`;
    }

    if (type === "months") {
      const months = (monthsCsv || "")
        .split(",")
        .map(x => parseInt(String(x).trim(), 10))
        .filter(n => Number.isFinite(n) && n >= 1 && n <= 12)
        .sort((a, b) => a - b);

      if (!months.length) return `<span class="badge">-</span>`;
      return `<div class="months-list">
        ${months.map(m => `<span class="badge badge--month">${escapeHtml(MONTH_NAMES[String(m)] || MONTH_NAMES[m] || "")}</span>`).join("")}
      </div>`;
    }

    return `<span class="badge">-</span>`;
  }

  function updatePeriodCell(rowId, type, monthInt, monthsCsv) {
    const box = $("periodView_" + rowId);
    if (box) box.innerHTML = renderPeriodHtml(type, monthInt, monthsCsv);
  }

  function updateRoleCell(rowId, roleValue, roleLabelKz) {
    const box = $("roleView_" + rowId);
    if (!box) return;
    const text = roleLabelKz || roleValue || "-";
    box.innerHTML = `<span class="badge">${escapeHtml(text)}</span>`;
  }

  function pmSync() {
    const months = [];
    document.querySelectorAll(".pm-month-cb").forEach(cb => {
      if (cb.checked) months.push(parseInt(cb.value, 10));
    });
    months.sort((a, b) => a - b);
    const val = months.join(",");

    const pv = $("pm_period_values");
    const pr = $("pm_preview");
    if (pv) pv.value = val;
    if (pr) pr.textContent = val || "—";
  }

  function periodModalToggle() {
    const ptEl = $("pm_period_type");
    if (!ptEl) return;

    const pt = ptEl.value;

    const blockMonth   = $("pm_block_month");
    const blockMonths  = $("pm_block_months");
    const blockQuarter = $("pm_block_quarter");

    if (blockMonth)   blockMonth.style.display   = (pt === "month")   ? "block" : "none";
    if (blockMonths)  blockMonths.style.display  = (pt === "months")  ? "block" : "none";
    if (blockQuarter) blockQuarter.style.display = (pt === "quarter") ? "block" : "none";

    if (pt !== "month") {
      const m = $("pm_month");
      if (m) m.value = "1";
    }

    if (pt !== "months") {
      const pv = $("pm_period_values");
      const pr = $("pm_preview");
      if (pv) pv.value = "";
      if (pr) pr.textContent = "—";
      document.querySelectorAll(".pm-month-cb").forEach(cb => cb.checked = false);
    } else {
      pmSync();
    }
  }

  // ✅ ВАЖНО: надёжно строим action, даже если data-action нет
  function buildActionUrl(rowId, btn) {
    // 1) если есть data-action — используем
    const fromBtn = (btn?.dataset?.action || "").trim();
    if (fromBtn) return fromBtn;

    // 2) если в форме уже есть action — используем
    const formAction = ($("metaForm")?.getAttribute("action") || "").trim();
    if (formAction) return formAction;

    // 3) попробуем взять с page-meta
    const meta = $("page-meta");
    const planId = meta?.dataset?.schoolPlanId;
    const directionId = meta?.dataset?.directionId;
    if (planId && directionId && rowId) {
      return `/planning/school/${planId}/direction/${directionId}/rows11/${rowId}/meta`;
    }

    // 4) ✅ ФОЛБЭК: распарсим текущий URL страницы /planning/school/{plan}/direction/{dir}
    const m = window.location.pathname.match(/^\/planning\/school\/(\d+)\/direction\/(\d+)/);
    if (m && rowId) {
      const plan = m[1];
      const dir = m[2];
      return `/planning/school/${plan}/direction/${dir}/rows11/${rowId}/meta`;
    }

    return ""; // пусть дальше покажем понятную ошибку
  }

  // ===== RESPONSIBLES MULTI =====
  function rmSync() {
    const picked = [];
    const labels = [];

    document.querySelectorAll(".rm-role-cb").forEach(cb => {
      if (cb.checked) {
        picked.push(cb.value);
        const lbl = cb.dataset.label || cb.parentElement?.querySelector("span")?.textContent?.trim();
        if (lbl) labels.push(lbl);
      }
    });

    const hidden = $("rm_roles");
    const preview = $("rm_preview");
    if (hidden) hidden.value = JSON.stringify(picked);
    if (preview) preview.textContent = labels.length ? labels.join(", ") : "—";
  }

  function rmSetFromJson(jsonStr) {
    let arr = [];
    try { arr = JSON.parse(jsonStr || "[]"); } catch (e) { arr = []; }
    const set = new Set(arr);

    document.querySelectorAll(".rm-role-cb").forEach(cb => {
      cb.checked = set.has(cb.value);
    });

    rmSync();
  }

  function renderRolesHtml(values, labelsMap) {
    if (!Array.isArray(values) || !values.length) {
      return `<span class="badge">-</span>`;
    }

    return `<div class="months-list">
          ${values.map(v => {
        const key = typeof v === "string" ? v : v?.role || "";
        const label = labelsMap && labelsMap[key] ? labelsMap[key] : key;
        return `<span class="badge badge--month">${escapeHtml(label)}</span>`;
      }).join("")}
    </div>`;
  }

  function updateRolesCell(rowId, rolesArr, labelsMap) {
    const box = document.getElementById(`roleView_${rowId}`);
    if (!box) return;

    if (!rolesArr || rolesArr.length === 0) {
      box.innerHTML = `<span class="badge">-</span>`;
      return;
    }

    box.innerHTML = rolesArr.map(v => {
      const label = (labelsMap && labelsMap[v]) ? labelsMap[v] : v;
      return `<span class="badge">${label}</span>`;
    }).join(" ");
  }

  function fillAndOpenFromDataset(btn) {
    const rowId = btn.dataset.rowId;
    const periodType = btn.dataset.periodType || "all_year";
    const periodValueIntRaw = btn.dataset.periodValueInt;
    const periodValueInt = periodValueIntRaw ? parseInt(periodValueIntRaw, 10) : null;
    const periodValues = (btn.dataset.periodValues || "").trim();
    const rolesJson = btn.dataset.roles || "[]";

    const form = $("metaForm");
    if (!form) {
      console.error("metaForm not found");
      return;
    }

    const action = buildActionUrl(rowId, btn);
    if (!action) {
      alert("Не удалось определить URL для сохранения.");
      return;
    }
    form.action = action;

    const mm = $("mm_row_id");
    if (mm) mm.value = rowId;

    const pt = $("pm_period_type");
    if (pt) pt.value = periodType;

    const monthEl = $("pm_month");
    if (monthEl) monthEl.value = periodValueInt != null ? String(periodValueInt) : "1";

    const months = periodValues
      ? periodValues.split(",")
          .map(x => parseInt(String(x).trim(), 10))
          .filter(n => Number.isFinite(n))
      : [];

    const pv = $("pm_period_values");
    if (pv) pv.value = months.join(",");

    document.querySelectorAll(".pm-month-cb").forEach(cb => {
          cb.checked = months.includes(parseInt(cb.value, 10));
    });

    if (typeof rmSetFromJson === "function") {
      rmSetFromJson(rolesJson);
    }

    periodModalToggle();
    pmSync();
    openModal("metaModal");
  }

  function updateRow11MetaDatasets(rowId, data, fallbackRolesArr) {
    // найдём кнопку редактирования для этой строки
    const btn = document.querySelector(`.js-open-meta[data-row-id="${rowId}"]`);
    if (!btn) return;

    // обновим периодные data-* чтобы тоже не отставали
    if (data && typeof data === "object") {
      if (data.period_type != null) btn.dataset.periodType = data.period_type;
      if (data.period_value_int != null) btn.dataset.periodValueInt = String(data.period_value_int);
      if ("period_values" in data) btn.dataset.periodValues = (data.period_values || "");
    }

    // ✅ обновим роли (главное)
    const roles = (data && Array.isArray(data.responsible_roles))
      ? data.responsible_roles
      : (fallbackRolesArr || []);

    btn.dataset.roles = JSON.stringify(roles);
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.addEventListener("click", (e) => {
      const closeBtn = e.target.closest("[data-modal-close]");
      if (closeBtn) closeModal(closeBtn.dataset.modalClose);
    });

    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".js-open-meta");
      if (btn) fillAndOpenFromDataset(btn);
    });

    $("pm_period_type")?.addEventListener("change", periodModalToggle);
    document.querySelectorAll(".pm-month-cb").forEach(cb => cb.addEventListener("change", pmSync));

    $("pm_select_all")?.addEventListener("click", () => {
      document.querySelectorAll(".pm-month-cb").forEach(cb => cb.checked = true);
      pmSync();
    });
    $("pm_clear_all")?.addEventListener("click", () => {
      document.querySelectorAll(".pm-month-cb").forEach(cb => cb.checked = false);
      pmSync();
    });
        // responsibles multi
    document.querySelectorAll(".rm-role-cb").forEach(cb => cb.addEventListener("change", rmSync));

    $("rm_select_all")?.addEventListener("click", () => {
      document.querySelectorAll(".rm-role-cb").forEach(cb => cb.checked = true);
      rmSync();
    });
    $("rm_clear_all")?.addEventListener("click", () => {
      document.querySelectorAll(".rm-role-cb").forEach(cb => cb.checked = false);
      rmSync();
    });
    const metaForm = $("metaForm");
    if (metaForm) {
      metaForm.addEventListener("submit", async (e) => {
        // ✅ если форма НЕ ajax — пусть браузер отправляет обычным способом
        if (metaForm.dataset.ajax !== "1") return;

        e.preventDefault();

        // ✅ если action пустой — даже не пытаемся, иначе улетит на текущую страницу и будет 405
        const action = (metaForm.action || "").trim();
        if (!action) {
          alert("Ошибка: form.action пустой. Нужен action или data-action.");
          return;
        }

        const btn = $("mm_submit");
        if (btn) btn.disabled = true;

        const rowId = $("mm_row_id")?.value;

        const type = $("pm_period_type")?.value || "all_year";
        const monthInt = (type === "month") ? parseInt($("pm_month")?.value || "1", 10) : null;
        const monthsCsv = (type === "months") ? ($("pm_period_values")?.value || "") : "";
        const rolesArr = Array.from(document.querySelectorAll(".rm-role-cb:checked"))
            .map(cb => cb.value);

        try {
          const resp = await fetch(action, {
            method: "POST",
            headers: { "X-Requested-With": "XMLHttpRequest" },
            body: new FormData(metaForm),
          });

          if (!resp.ok) {
            const body = await resp.text();
            throw new Error(body || ("HTTP " + resp.status));
          }

          const data = await fetchJsonOrText(resp);

          if (data && typeof data === "object") {

            updatePeriodCell(
              rowId,
              data.period_type || type,
              data.period_value_int ?? monthInt,
              data.period_values ?? monthsCsv
            );

            // всегда рисуем то, что выбрал пользователь
            updateRolesCell(
              rowId,
              rolesArr,
              data.responsible_labels_kz || null
            );

            // ✅ ОБНОВЛЯЕМ dataset кнопки (чтобы модалка не отставала)
            updateRow11MetaDatasets(rowId, {
              period_type: data.period_type || type,
              period_value_int: data.period_value_int ?? monthInt,
              period_values: data.period_values ?? monthsCsv,
              responsible_roles: rolesArr
            }, rolesArr);

          } else {

            updatePeriodCell(rowId, type, monthInt, monthsCsv);
            updateRolesCell(rowId, rolesArr, null);

            // ✅ даже если сервер ничего не вернул — обновим dataset
            updateRow11MetaDatasets(rowId, {
              period_type: type,
              period_value_int: monthInt,
              period_values: monthsCsv,
              responsible_roles: rolesArr
            }, rolesArr);
          }

          closeModal("metaModal");
        } catch (err) {
          alert("Ошибка сохранения: " + (err?.message || err));
          console.error(err);
        } finally {
          if (btn) btn.disabled = false;
        }
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeModal("metaModal");
    });
  });
})();