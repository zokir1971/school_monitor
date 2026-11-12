(() => {
  'use strict';
  function reserveActionSpace() {
    const page = document.querySelector('.monthly-plan-page');
    const actions = page?.querySelector('.monthly-plan-actions');
    if (!actions) return;
    const measure = () => page.style.setProperty('--monthly-plan-actions-height', `${Math.ceil(actions.getBoundingClientRect().height)}px`);
    measure();
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(measure).observe(actions);
    window.addEventListener('resize', measure, {passive: true});
    document.fonts?.ready.then(measure);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', reserveActionSpace, {once:true});
  else reserveActionSpace();
})();
