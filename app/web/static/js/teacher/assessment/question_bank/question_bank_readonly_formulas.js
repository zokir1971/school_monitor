/* Read-only legacy formulas: display only; never changes stored segments. */
(() => {
  function render() {
    const selector = '.qb-segment-text, .qb-question-text, .qb-review-question, .qb-render-option__body, .qb-review-answer-key';
    const roots = [...document.querySelectorAll(selector)];
    const nodes = new Set();
    roots.forEach(root => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          return node.parentElement.closest('math-field, script, style, textarea, input, [contenteditable="true"], [data-qb-legacy-formula]')
            ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
        }
      });
      while (walker.nextNode()) nodes.add(walker.currentNode);
    });
    nodes.forEach(node => {
      const value = node.textContent;
      const pattern = /\$\$([\s\S]+?)\$\$|\\\(([\s\S]+?)\\\)|\\\[([\s\S]+?)\\\]|([A-Za-z0-9_{}^=+*/().<>|,:;!\-]*\\[A-Za-z]+(?:\{[^\n]*?\}|[A-Za-z0-9_{}^=+*/().<>|,:;!\\\-])*)/g;
      const matches = [...value.matchAll(pattern)];
      if (!matches.length) return;
      const fragment = document.createDocumentFragment();
      let offset = 0;
      matches.forEach(match => {
        fragment.append(document.createTextNode(value.slice(offset, match.index)));
        const field = document.createElement('math-field');
        field.dataset.qbLegacyFormula = '';
        field.setAttribute('read-only', '');
        field.setAttribute('math-virtual-keyboard-policy', 'manual');
        field.tabIndex = -1;
        field.textContent = match[1] ?? match[2] ?? match[3] ?? match[4];
        field.style.cssText = 'display:inline-block;max-width:100%;vertical-align:middle;border:0;background:transparent;font-size:1.1em;pointer-events:none;';
        fragment.append(field);
        offset = match.index + match[0].length;
      });
      fragment.append(document.createTextNode(value.slice(offset)));
      node.replaceWith(fragment);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', render);
  else render();
})();
