/* Fit existing text fields without changing values or form submission. */
(function () {
  const form = document.querySelector('.row11-form');
  if (!form) return;
  const fields = Array.from(form.querySelectorAll('textarea.row11-textarea'));
  const pending = new Set();
  let frame = 0;
  function fit(field) {
    if (!field.getClientRects().length) return;
    const style = getComputedStyle(field);
    const border = (parseFloat(style.borderTopWidth) || 0) + (parseFloat(style.borderBottomWidth) || 0);
    const minimum = parseFloat(style.minHeight) || 43;
    // Reset first so deleting text can shrink a previously tall field.
    field.style.height = 'auto';
    field.style.overflowY = 'hidden';
    field.style.height = Math.max(minimum, field.scrollHeight + border) + 'px';
  }
  function schedule(field) {
    pending.add(field);
    if (frame) return;
    frame = requestAnimationFrame(function () {
      frame = 0;
      pending.forEach(fit);
      pending.clear();
    });
  }
  function fitAll() { fields.forEach(schedule); }
  fields.forEach(function (field) {
    field.addEventListener('input', function () { schedule(field); });
  });
  window.addEventListener('resize', fitAll);
  window.addEventListener('pageshow', fitAll);
  form.addEventListener('reset', function () { requestAnimationFrame(fitAll); });
  if (typeof ResizeObserver !== 'undefined') {
    let width = form.getBoundingClientRect().width;
    new ResizeObserver(function () {
      const next = form.getBoundingClientRect().width;
      if (Math.abs(next - width) < 1) return;
      width = next;
      fitAll();
    }).observe(form);
  }
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitAll);
  fitAll();
})();
