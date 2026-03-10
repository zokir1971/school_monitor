// static/js/row11_inline_save.js
(function () {
  async function postJson(url, payload) {
    let resp;
    try {
      resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      throw new Error("Network error");
    }

    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(txt || ("HTTP " + resp.status));
    }
  }

  function togglePeriodUI(rowId, type) {
    const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
    if (!row) return;

    const blockMonth   = row.querySelector(".js-period-month");
    const blockMonths  = row.querySelector(".js-period-months");
    const blockQuarter = row.querySelector(".js-period-quarter");

    if (blockMonth)   blockMonth.style.display   = (type === "month")   ? "" : "none";
    if (blockMonths)  blockMonths.style.display  = (type === "months")  ? "" : "none";
    if (blockQuarter) blockQuarter.style.display = (type === "quarter") ? "" : "none";
  }

  // Переключение типа периода
  document.addEventListener("change", (e) => {
    const sel = e.target.closest(".js-period-type");
    if (!sel) return;
    togglePeriodUI(sel.dataset.rowId, sel.value);
  });

  // Кнопки сохранения
  document.addEventListener("click", async (e) => {
    // ===================== SAVE PERIOD =====================
    const btnPeriod = e.target.closest(".js-save-period");
    if (btnPeriod) {
      const rowId = btnPeriod.dataset.rowId;
      const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
      if (!row) return;

      const type = row.querySelector(".js-period-type")?.value || null;
      const month = row.querySelector(".js-month")?.value || "";
      const quarter = row.querySelector(".js-quarter")?.value || "";
      let monthsText = row.querySelector(".js-months-text")?.value || "";

      // normalize months: "1, 2,3" -> "1,2,3"
      monthsText = monthsText
        .split(",")
        .map(s => s.trim())
        .filter(Boolean)
        .join(",");

      btnPeriod.disabled = true;

      try {
        await postJson(`/api/rows11/${rowId}/period`, {
          period_type: type,
          month: month ? Number(month) : null,
          quarter: quarter ? Number(quarter) : null,
          period_values: monthsText || null,
        });

        const oldText = btnPeriod.textContent;
        btnPeriod.textContent = "✓";
        setTimeout(() => (btnPeriod.textContent = oldText || "Сохранить"), 800);
      } catch (err) {
        alert("Ошибка сохранения периода: " + (err?.message || err));
      } finally {
        btnPeriod.disabled = false;
      }

      return;
    }

    // ===================== SAVE RESPONSIBLE ROLE =====================
    const btnRole = e.target.closest(".js-save-role");
    if (btnRole) {
      const rowId = btnRole.dataset.rowId;
      const row = document.querySelector(`tr[data-row-id="${rowId}"]`);
      if (!row) return;

      const role = row.querySelector(".js-resp-role")?.value || null;

      btnRole.disabled = true;

      try {
        await postJson(`/api/rows11/${rowId}/responsible-role`, {
          responsible_role: role,
        });

        const oldText = btnRole.textContent;
        btnRole.textContent = "✓";
        setTimeout(() => (btnRole.textContent = oldText || "Сохранить"), 800);
      } catch (err) {
        alert("Ошибка сохранения роли: " + (err?.message || err));
      } finally {
        btnRole.disabled = false;
      }

      return;
    }
  });
})();