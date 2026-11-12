/* One count on navigation; throttled refresh when returning to this tab. */
(() => {
  'use strict';
  const link = document.querySelector('[data-internal-notices]');
  if (!link) return;
  const badge = link.querySelector('[data-notice-count]');
  let busy = false, last = 0;
  async function refresh() {
    if (busy || document.hidden || Date.now() - last < 30000) return;
    busy = true; last = Date.now();
    try {
      const response = await fetch(link.dataset.countUrl, {credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json'}});
      if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) return;
      const body = await response.json();
      if (!Number.isSafeInteger(body.unread) || body.unread < 0) return;
      badge.hidden = body.unread === 0;
      badge.textContent = String(body.unread);
    } catch (_) { /* The inbox link remains usable if the badge request fails. */ }
    finally { busy = false; }
  }
  refresh();
  window.addEventListener('focus',refresh);
  document.addEventListener('visibilitychange',refresh);
})();
