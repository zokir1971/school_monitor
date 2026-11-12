"use strict";
document.addEventListener("submit", function (event) {
  const form = event.target;
  if (!form.matches("form[data-qb-delete-set]")) return;
  if (!window.confirm(form.dataset.confirm)) event.preventDefault();
});
