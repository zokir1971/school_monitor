/* Progressive disclosure only: no requests, no replacement save/delete logic. */
(function () {
  const root = document.getElementById('pageRoot');
  if (!root) return;
  function expand(button, open) {
    const details = document.getElementById(button.getAttribute('aria-controls'));
    if (!details) return;
    details.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    button.textContent = open ? button.dataset.closeLabel : button.dataset.openLabel;
    button.closest('tr').classList.toggle('is-expanded', open);
  }
  root.addEventListener('click', function (event) {
    const button = event.target.closest('button[data-task-toggle]');
    if (!button || !root.contains(button)) return;
    event.preventDefault();
    expand(button, button.getAttribute('aria-expanded') !== 'true');
  });
  function revealAnchor() {
    const match = /^#row11-(\d+)$/.exec(window.location.hash);
    if (!match) return;
    const row = document.getElementById('row11-' + match[1]);
    const button = row && row.querySelector('[data-task-toggle]');
    if (button) expand(button, true);
  }
  const header = document.querySelector('.header, header');
  function alignHeader() {
    root.style.setProperty('--direction-header-height', (header ? Math.max(0, header.getBoundingClientRect().bottom) : 0) + 'px');
  }
  alignHeader();
  window.addEventListener('resize', alignHeader);
  window.addEventListener('hashchange', revealAnchor);
  if (header && typeof ResizeObserver !== 'undefined') new ResizeObserver(alignHeader).observe(header);
  revealAnchor();
  const description = document.getElementById('directionDescription');
  if (description) {
    const key = 'sm-direction-description:' + root.dataset.planId + ':' + root.dataset.directionId;
    try { description.open = sessionStorage.getItem(key) === 'open'; } catch (_) {}
    description.addEventListener('toggle', function () {
      try { sessionStorage.setItem(key, description.open ? 'open' : 'closed'); } catch (_) {}
    });
  }
})();
