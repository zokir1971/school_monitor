// static/js/row_select.js
(function () {
  // выбранный row_id для каждого kind
  const selected = { row4: null, row11: null };

  function clearSelection(kind) {
    document
      .querySelectorAll(`tr[data-row][data-kind="${kind}"]`)
      .forEach((tr) => tr.classList.remove("row-selected"));

    selected[kind] = null;

    const btn = document.getElementById(`btnDelete-${kind}`);
    if (btn) {
      btn.disabled = true;
      delete btn.dataset.selectedRowId;
    }
  }

  function selectRow(tr) {
    const kind = tr.dataset.kind;          // "row4" | "row11"
    const rowId = tr.dataset.rowId;
    const isCustom = tr.dataset.isCustom === "1";

    // снять выделение с остальных строк этого kind
    document
      .querySelectorAll(`tr[data-row][data-kind="${kind}"]`)
      .forEach((x) => x.classList.remove("row-selected"));

    tr.classList.add("row-selected");
    selected[kind] = rowId;

    const btn = document.getElementById(`btnDelete-${kind}`);
    if (btn) {
      btn.disabled = !isCustom;
      btn.dataset.selectedRowId = rowId;
    }
  }

  function buildDeleteUrl(kind, planId, directionId, rowId) {
    const seg = kind === "row4" ? "rows4" : "rows11";
    return `/planning/school/${planId}/direction/${directionId}/${seg}/${rowId}/delete`;
  }

  function wireDeleteButton(kind) {
    const btn = document.getElementById(`btnDelete-${kind}`);
    const form = document.getElementById(`deleteForm-${kind}`);
    const root = document.getElementById("pageRoot");

    if (!btn || !form || !root) return;

    btn.addEventListener("click", function () {
      const rowId = selected[kind];
      if (!rowId) return;

      if (!confirm("Удалить выбранную строку?")) return;

      const planId = root.dataset.planId;
      const directionId = root.dataset.directionId;
      if (!planId || !directionId) return;

      form.action = buildDeleteUrl(kind, planId, directionId, rowId);
      form.submit();
    });
  }

  function wireRowClicks() {
    // ✅ выбираем ТОЛЬКО по клику на нумерацию
    // В HTML на td нумерации поставь: data-select-cell
    // Например:
    // <td class="cell cell--select" data-select-cell> ... </td>
    document.addEventListener("click", function (e) {
      console.log("clicked", e.target);

      const cell = e.target.closest("[data-select-cell]");
      console.log("cell?", cell);

      if (!cell) return;

      const tr = cell.closest('tr[data-row][data-kind][data-row-id]');
      console.log("tr?", tr);

      if (!tr) return;
      selectRow(tr);
    }, true);
  }

  function init() {
    wireRowClicks();
    wireDeleteButton("row4");
    wireDeleteButton("row11");

    // (опционально) сброс выбора кликом вне таблиц:
    // document.addEventListener("click", (e) => {
    //   if (!e.target.closest("table")) {
    //     clearSelection("row4");
    //     clearSelection("row11");
    //   }
    // }, true);
  }

  document.addEventListener("DOMContentLoaded", init);
})();