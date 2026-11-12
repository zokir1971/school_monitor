/* Transfer only the clicked task's draft week and inclusion choice. Persistence is POST-only. */
(() => {
  'use strict';
  document.addEventListener('click', event => {
    const link = event.target.closest('a.monthly-plan-assign');
    if (!link) return;
    const url = new URL(link.href, location.href);
    const match = url.pathname.match(/^\/planning\/school\/monthly\/(\d+)\/assignees$/);
    if (!match || url.origin !== location.origin) return;
    const included = document.querySelector('[name="item_' + match[1] + '_included"]');
    if (included && !included.disabled) url.searchParams.set('draft_included', included.checked ? '1' : '0');
    const week = document.querySelector('[name="item_' + match[1] + '_week"]');
    if (week && !week.disabled) url.searchParams.set('draft_week', week.value);
    link.href = url.href;
  }, true);
})();
