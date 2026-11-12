/* Progressive enhancement: the original select owns validation and submitted ID. */
(() => {
  'use strict';
  const languageFields = Array.from(document.querySelectorAll('[data-qb-objective-language]'));
  const pickers = [];
  const languages = new Set(['kk', 'ru', 'en']);
  const normalize = text => String(text || '').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
  const initial = languageFields[0]?.value
    || document.querySelector('[data-qb-objective-language-value]')?.value
    || document.querySelector('[data-qb-rich-objective-picker]')?.dataset.language || 'kk';
  let language = languages.has(initial) ? initial : 'kk';

  function syncDisplays() {
    document.querySelectorAll('[data-qb-objective-language-value]').forEach(input => { input.value = language; });
    document.querySelectorAll('[data-qb-objective-display]').forEach(container => {
      container.querySelectorAll('[data-objective-display-language]').forEach(node => {
        node.hidden = node.dataset.objectiveDisplayLanguage !== language;
      });
    });
  }

  document.querySelectorAll('[data-qb-rich-objective-picker]').forEach((root, index) => {
    const select = root.querySelector('select[data-qb-objective-select]');
    if (!select || select.multiple) return;
    const id = select.id || 'qb-objective-picker-' + index;
    const label = root.querySelector('label');
    const sources = new Map();
    root.querySelectorAll('template[data-qb-picker-option]').forEach(template => {
      sources.set(template.dataset.value + ':' + template.dataset.language, template);
    });
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'qb-objective-trigger';
    trigger.id = id + '-trigger';
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-haspopup', 'dialog');
    trigger.setAttribute('aria-expanded', 'false');
    if (select.required) trigger.setAttribute('aria-required', 'true');
    if (label) {
      label.htmlFor = trigger.id;
      trigger.setAttribute('aria-labelledby', label.id + ' ' + id + '-selected');
    }
    const selected = document.createElement('span');
    selected.id = id + '-selected';
    selected.className = 'qb-objective-selected';
    const caret = document.createElement('span');
    caret.className = 'qb-objective-caret';
    caret.setAttribute('aria-hidden', 'true');
    caret.textContent = '▼';
    trigger.append(selected, caret);
    const popup = document.createElement('div');
    popup.className = 'qb-objective-popup';
    popup.id = id + '-popup';
    popup.hidden = true;
    popup.setAttribute('role', 'dialog');
    popup.setAttribute('aria-label', window.SchoolMonitorI18n.t("qb_6e9caf1ee06f"));
    trigger.setAttribute('aria-controls', popup.id);
    const search = document.createElement('input');
    search.type = 'search';
    search.className = 'qb-objective-search';
    search.placeholder = window.SchoolMonitorI18n.t("qb_2a6dd12160d3");
    search.setAttribute('aria-label', window.SchoolMonitorI18n.t("qb_58e14a4ba981"));
    const list = document.createElement('div');
    list.className = 'qb-objective-options';
    list.id = id + '-options';
    list.setAttribute('role', 'listbox');
    if (label) list.setAttribute('aria-labelledby', label.id);
    const empty = document.createElement('p');
    empty.className = 'qb-objective-empty';
    empty.textContent = window.SchoolMonitorI18n.t("qb_f16e22ed91c4");
    empty.setAttribute('role', 'status');
    popup.append(search, list, empty);
    select.after(trigger, popup);
    let entries = [];

    function content(target, option) {
      target.replaceChildren();
      const template = sources.get(option.value + ':' + language);
      if (template) target.append(template.content.cloneNode(true));
      else target.textContent = option.textContent;
      target.querySelectorAll('math-field').forEach(field => {
        field.setAttribute('read-only', '');
        field.setAttribute('tabindex', '-1');
        field.removeAttribute('name');
      });
    }
    function close(focus = false) {
      popup.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
      if (focus) trigger.focus();
    }
    function choose(option) {
      select.value = option.value;
      select.dispatchEvent(new Event('input', {bubbles:true}));
      select.dispatchEvent(new Event('change', {bubbles:true}));
      close(true);
    }
    function filtered() { return entries.filter(entry => !entry.node.hidden); }
    function focusEntry(position) {
      const visible = filtered();
      if (!visible.length) return;
      const entry = visible[(position + visible.length) % visible.length];
      entries.forEach(item => { item.node.tabIndex = item === entry ? 0 : -1; });
      entry.node.focus();
      entry.node.scrollIntoView?.({block:'nearest'});
    }
    function filter() {
      const words = normalize(search.value).split(' ').filter(Boolean);
      entries.forEach(entry => { entry.node.hidden = !words.every(word => entry.text.includes(word)); });
      empty.hidden = filtered().length > 0;
    }
    function refresh() {
      trigger.disabled = select.disabled;
      const current = select.selectedOptions[0];
      if (current?.value) content(selected, current);
      else selected.textContent = root.dataset.allowEmpty === "1" ? (current?.textContent || "") : window.SchoolMonitorI18n.t("qb_98781bc6106c");
      trigger.removeAttribute('aria-invalid');
      list.replaceChildren();
      entries = Array.from(select.options).filter(option => (option.value || root.dataset.allowEmpty === "1") && !option.disabled).map(option => {
        const row = document.createElement('div');
        row.className = 'qb-objective-option';
        row.tabIndex = -1;
        row.setAttribute('role', 'option');
        row.setAttribute('aria-selected', String(option.value === select.value));
        row.dataset.value = option.value;
        content(row, option);
        row.addEventListener('click', () => choose(option));
        row.addEventListener('keydown', event => {
          const visible = filtered();
          const position = visible.findIndex(entry => entry.node === row);
          if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(option); }
          else if (event.key === 'ArrowDown') { event.preventDefault(); focusEntry(position + 1); }
          else if (event.key === 'ArrowUp') { event.preventDefault(); focusEntry(position - 1); }
          else if (event.key === 'Home') { event.preventDefault(); focusEntry(0); }
          else if (event.key === 'End') { event.preventDefault(); focusEntry(visible.length - 1); }
        });
        list.append(row);
        return {node:row, text:normalize(row.textContent), option};
      });
      filter();
    }
    function open(focusOptions = false) {
      if (trigger.disabled) return;
      pickers.forEach(picker => { if (picker.close !== close) picker.close(); });
      search.value = '';
      filter();
      popup.hidden = false;
      trigger.setAttribute('aria-expanded', 'true');
      if (focusOptions) {
        const visible = filtered();
        const current = visible.findIndex(entry => entry.option.value === select.value);
        focusEntry(current >= 0 ? current : 0);
      } else search.focus();
    }
    trigger.addEventListener('click', () => popup.hidden ? open() : close());
    trigger.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault(); open(true);
      }
    });
    search.addEventListener('input', filter);
    search.addEventListener('keydown', event => {
      if (event.key === 'Enter') {
        event.preventDefault();
        const visible = filtered();
        if (visible.length === 1) choose(visible[0].option);
        else focusEntry(0);
      } else if (event.key === 'ArrowDown') { event.preventDefault(); focusEntry(0); }
      else if (event.key === 'ArrowUp') { event.preventDefault(); focusEntry(filtered().length - 1); }
    });
    root.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !popup.hidden) {
        event.preventDefault(); event.stopPropagation(); close(true);
      }
    });
    root.addEventListener('focusout', event => {
      if (event.relatedTarget && !root.contains(event.relatedTarget)) close();
    });
    document.addEventListener('pointerdown', event => { if (!root.contains(event.target)) close(); });
    select.addEventListener('change', refresh);
    select.addEventListener('invalid', event => {
      event.preventDefault();
      open();
      trigger.setAttribute('aria-invalid', 'true');
    });
    select.form?.addEventListener('reset', () => setTimeout(() => { close(); refresh(); }, 0));
    window.addEventListener('pageshow', () => { close(); refresh(); });
    const picker = {refresh, close};
    pickers.push(picker);
    refresh();
    select.hidden = true; // Name, value, required and event listeners remain intact.
  });

  function setLanguage(value) {
    if (!languages.has(value)) return;
    language = value;
    languageFields.forEach(field => { field.value = value; });
    syncDisplays();
    pickers.forEach(picker => { picker.close(); picker.refresh(); });
  }
  languageFields.forEach(field => field.addEventListener('change', () => setLanguage(field.value)));
  setLanguage(language);
})();
