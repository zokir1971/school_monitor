/* Native details handles Enter/Space and Tab; add Escape, outside click and one disclosure at a time. */
(() => {
  'use strict';
  const header = document.querySelector('.sm-site-header');
  if (!header) return;
  const menus = [...header.querySelectorAll('details.sm-user-menu,details.workspace-menu')];
  for (const menu of menus) {
    menu.addEventListener('toggle', () => {
      if (menu.open) menus.forEach(other => { if (other !== menu) other.open = false; });
    });
    menu.addEventListener('focusout', event => {
      // Focus can temporarily be on body between pointerdown and click.
      // Never hide a submit button during that transition: inspect the destination,
      // not document.activeElement. Outside pointerdown and Escape handle null targets.
      if (event.relatedTarget && !menu.contains(event.relatedTarget)) menu.open = false;
    });
  }
  document.addEventListener('pointerdown', event => {
    menus.forEach(menu => { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    menus.forEach(menu => {
      if (!menu.open) return;
      const inside = menu.contains(document.activeElement);
      menu.open = false;
      if (inside) { menu.querySelector('summary').focus(); event.preventDefault(); }
    });
  });
})();
