/* Bounded, text-only tree editor. No HTML from generated content is interpreted. */
(() => {
  'use strict';
  const root = document.getElementById('qb-recovery-editor');
  if (!root) return;
  const form = document.getElementById('qb-recovery-form');
  const raw = document.getElementById('qb-recovery-json');
  const labels = JSON.parse(document.getElementById('qb-recovery-labels').textContent);
  let data = JSON.parse(document.getElementById('qb-recovery-data').textContent);
  const name = key => key.startsWith('/') ? key.slice(1).split('/').map(part => /^\d+$/.test(part) ? String(Number(part)+1) : labels[part] || part).join(' / ') : labels[key] || key;
  const el = (tag, text) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; return node; };
  const sync = () => { raw.value = JSON.stringify(data, null, 2); renderPreview(); };
  const clone = value => JSON.parse(JSON.stringify(value));
  const button = (text, action) => { const node = el('button', text); node.type = 'button'; node.addEventListener('click', action); return node; };
  function renderValue(value, key, set, path, depth = 0) {
    if (depth > 30) throw new Error(labels.invalid);
    const fixed = path[0]==='source' && ['question_type','difficulty','max_score','learning_objective_ids'].includes(String(path[1]));
    if (fixed && value !== null && typeof value === 'object') {
      const line=el('p', name(String(key))+': '+JSON.stringify(value)); return line;
    }
    if (value !== null && typeof value === 'object') {
      const group = el('fieldset'); group.append(el('legend', name(String(key))));
      if (Array.isArray(value)) {
        value.forEach((child, index) => {
          const row = el('div');
          row.append(renderValue(child, String(index + 1), v => { value[index] = v; sync(); }, [...path, index], depth + 1));
          row.append(button(labels.remove, () => { value.splice(index, 1); sync(); render(); }));
          group.append(row);
        });
        group.append(button(labels.add, () => {
          if (value.length >= 100) return;
          value.push(value.length ? clone(value[value.length - 1]) : ''); sync(); render();
        }));
      } else {
        const entries=Object.entries(value);
        if(path.length===1) entries.sort(([a],[b]) => fieldRank(a)-fieldRank(b) || a.localeCompare(b,undefined,{numeric:true}));
        entries.forEach(([childKey, child]) => {
          if (path.length===1 && path[0]==='source' && childKey==='text' && Array.isArray(value.text_segments)) return;
          const row = el('div');
          row.append(renderValue(child, childKey, v => { value[childKey] = v; sync(); }, [...path, childKey], depth + 1));
          // Legacy text maps may include forbidden math fields. Removing such
          // a field is an explicit user edit, never an automatic repair.
          if (path.length === 1 && path[0] === 'translation' && childKey.startsWith('/')) {
            row.append(button(labels.remove, () => { delete value[childKey]; sync(); render(); }));
          }
          group.append(row);
        });
      }
      return group;
    }
    const label = el('label', name(String(key)));
    let control;
    if (typeof value === 'boolean') {
      control = el('select');
      [true, false].forEach(v => { const option = el('option', v ? labels.yes : labels.no); option.value = String(v); control.append(option); });
      control.value = String(value);
      control.addEventListener('change', () => set(control.value === 'true'));
    } else if (key === 'type' && ['text', 'latex'].includes(value)) {
      control = el('select');
      ['text', 'latex'].forEach(v => { const option = el('option', v); option.value = v; control.append(option); });
      control.value = value; control.addEventListener('change', () => set(control.value));
    } else {
      control = el('textarea'); control.value = value === null ? '' : String(value);
      control.rows = String(value || '').length > 100 ? 3 : 2;
      control.addEventListener('input', () => {
        if (typeof value === 'number') {
          const numeric = Number(control.value);
          control.setCustomValidity(control.value.trim() && Number.isFinite(numeric) ? '' : labels.invalid);
          if (Number.isFinite(numeric)) set(numeric);
        } else { set(control.value); }
      });
    }
    if (fixed) control.disabled = true;
    control.setAttribute('aria-label', path.map(part => name(String(part))).join(' / '));
    label.append(control);
    if (String(key).startsWith('/')) {
      const hint = el('span', String(key)); hint.className = 'qb-recovery__path'; label.append(hint);
    }
    return label;
  }
  // Human reading order must not depend on JSON key order in a diagnostic.
  const fieldOrder=['title','text_segments','text','instruction','content','answer_key','grading_settings','explanation','author_comment'];
  function fieldRank(key) { const first=key.startsWith('/')?key.split('/')[1]:key; const rank=fieldOrder.indexOf(first); return rank<0?fieldOrder.length:rank; }
  function renderPreview() {
    const preview=document.getElementById('qb-recovery-preview');
    if(!preview) return;
    preview.replaceChildren();
    const source=data.source;
    if(!source || typeof source!=='object') return;
    if(typeof source.title==='string'&&source.title.trim()) preview.append(el('h4',source.title));
    function segments(items, fallback='') {
      const line=el('div'); line.className='qb-recovery__preview-line';
      if(Array.isArray(items)&&items.length) {
        items.forEach(segment=>{
          if(!segment||typeof segment!=='object') return;
          if(segment.type==='gap') { line.append(el('span',' ['+String(segment.id||segment.gap_id||'…')+'] ')); return; }
          if(typeof segment.text!=='string') return;
          if(segment.type==='latex') {
            const math=el('math-field',segment.text);math.setAttribute('read-only','');math.setAttribute('tabindex','-1');
            line.append(math);
          } else { line.append(el('span',segment.text)); }
        });
      } else if(typeof fallback==='string') { line.append(el('span',fallback)); }
      return line;
    }
    preview.append(segments(source.text_segments,source.text));
    if(typeof source.instruction==='string'&&source.instruction.trim()) preview.append(el('p',source.instruction));
    const prose=new Set(['label','title','description','prompt','statement','meaning','definition','text','hint','caption']);
    function content(node,path=[],depth=0) {
      if(depth>30||!node||typeof node!=='object') return;
      if(Array.isArray(node)) {
        node.forEach((value,index)=>{
          const identifier=value&&typeof value==='object'&&(value.value||value.id);
          content(value,[...path,String(identifier||index+1)],depth+1);
        });return;
      }
      for(const [key,value] of Object.entries(node)) {
        if(key==='segments'&&Array.isArray(value)) {
          const block=el('div');block.className='qb-recovery__preview-item';
          if(path.length) block.append(el('strong',path.map(name).join(' / ')));
          block.append(segments(value));preview.append(block);
        } else if(prose.has(key)&&typeof value==='string'&&value.trim()) {
          const block=el('div');block.className='qb-recovery__preview-item';
          if(path.length) block.append(el('strong',path.map(name).join(' / ')));
          block.append(el('span',value));preview.append(block);
        } else if(value&&typeof value==='object') content(value,[...path,key],depth+1);
      }
    }
    content(source.content);
  }
  function render() {
    renderPreview();
    root.replaceChildren();
    root.append(renderValue(data.source, 'source', v => { data.source = v; sync(); }, ['source']));
    root.append(renderValue(data.translation, 'translation', v => { data.translation = v; sync(); }, ['translation']));
  }
  document.getElementById('qb-recovery-apply').addEventListener('click', () => {
    const error = document.getElementById('qb-recovery-json-error');
    try {
      if (raw.value.length > 2000000) throw new Error();
      const candidate = JSON.parse(raw.value);
      if (!candidate || typeof candidate !== 'object' || !candidate.source || !candidate.translation) throw new Error();
      data = candidate; render(); error.textContent = ''; raw.setCustomValidity('');
    } catch (_) { error.textContent = labels.invalid; raw.setCustomValidity(labels.invalid); }
  });
  // Keep unapplied advanced edits visible rather than silently overwriting them.
  raw.addEventListener('input', () => raw.setCustomValidity(labels.invalid));
  form.addEventListener('submit', () => { if (!raw.validationMessage) sync(); });
  render();
})();
