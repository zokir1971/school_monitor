// static/js/cell_edit.js
(function () {
  const meta = document.getElementById("page-meta");
  const schoolPlanId = meta?.dataset.schoolPlanId;
  const directionId = meta?.dataset.directionId;

  if (!schoolPlanId || !directionId) {
    console.warn("cell_edit.js: missing #page-meta data-school-plan-id / data-direction-id");
    return;
  }

  const NON_EDITABLE_FIELDS = new Set(["no"]);
  const IGNORE_CLICK_SELECTOR =
    "button, a, input, select, textarea, label, .icon-btn, [data-no-edit], [data-modal-close]";

  function closestEditableTextEl(target) {
    const textEl = target.closest?.(".cell__text");
    if (!textEl) return null;
    const cell = textEl.closest(".cell");
    if (!cell) return null;

    const field = cell.dataset.field;
    if (!field || NON_EDITABLE_FIELDS.has(field)) return null;

    return { cell, textEl };
  }

  function enterEditMode(cell, textEl) {
    if (textEl.isContentEditable) return;

    const original = textEl.textContent ?? "";
    textEl.dataset.originalValue = original;

    textEl.contentEditable = "true";
    textEl.focus();

    // cursor to end
    const range = document.createRange();
    range.selectNodeContents(textEl);
    range.collapse(false);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    sel?.addRange(range);

    cell.classList.add("cell--editing");
  }

  async function saveCell(cell, textEl) {
    const kind = cell.dataset.kind;
    const rowId = cell.dataset.rowId;
    const field = cell.dataset.field;

    if (!field || NON_EDITABLE_FIELDS.has(field)) return true;

    const value = (textEl.textContent ?? "").trim();
    const original = (textEl.dataset.originalValue ?? "").trim();
    if (value === original) return true;

    cell.classList.remove("cell--error", "cell--saved");
    cell.classList.add("cell--saving");

    const payload = {
      kind,
      row_id: Number(rowId),
      field,
      value,
      school_plan_id: Number(schoolPlanId),
      direction_id: Number(directionId),
    };

    let resp;
    try {
      resp = await fetch("/api/cell", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
        },
        body: JSON.stringify(payload),
      });
    } catch (err) {
      cell.classList.remove("cell--saving");
      cell.classList.add("cell--error");
      console.error("cell_edit.js: network error", err);
      return false;
    }

    cell.classList.remove("cell--saving");

    if (!resp.ok) {
      const txt = await resp.text();
      console.error("cell_edit.js: save failed:", resp.status, txt);
      cell.classList.add("cell--error");
      return false;
    }

    cell.classList.add("cell--saved");
    setTimeout(() => cell.classList.remove("cell--saved"), 800);
    return true;
  }

  document.addEventListener("click", (e) => {
    if (e.target.closest(IGNORE_CLICK_SELECTOR)) return;

    const cell = e.target.closest(".cell");
    if (!cell) return;

    const field = cell.dataset.field;
    if (!field || NON_EDITABLE_FIELDS.has(field)) return;

    const textEl = cell.querySelector(".cell__text");
    if (!textEl) return;

    enterEditMode(cell, textEl);
  });

  document.addEventListener("keydown", (e) => {
    const info = closestEditableTextEl(e.target);
    if (!info) return;

    const { cell, textEl } = info;
    if (!textEl.isContentEditable) return;

    if (e.key === "Escape") {
      e.preventDefault();
      textEl.textContent = textEl.dataset.originalValue ?? "";
      textEl.contentEditable = "false";
      cell.classList.remove("cell--editing");
      return;
    }

    if (e.key === "Enter") {
      e.preventDefault();
      textEl.blur();
    }
  });

  document.addEventListener("focusout", async (e) => {
    const info = closestEditableTextEl(e.target);
    if (!info) return;

    const { cell, textEl } = info;
    if (!textEl.isContentEditable) return;

    textEl.contentEditable = "false";
    cell.classList.remove("cell--editing");

    const ok = await saveCell(cell, textEl);
    if (!ok) {
      textEl.textContent = textEl.dataset.originalValue ?? "";
    }
  });
})();