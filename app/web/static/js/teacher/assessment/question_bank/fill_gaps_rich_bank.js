/* Rich bank is versioned; strings and legacy text input keep their original contract. */
(() => {
  let attempts = 0;
  function init() {
    const group = document.getElementById('fill-gaps-fields');
    if (!group || group.dataset.richBankReady) return;
    const form = group.closest('form'), rich = window.QuestionRichEditor;
    const panel = group.querySelector('[data-rich-bank-panel]');
    const status = group.querySelector('[data-rich-bank-status]');
    const type = form.querySelector('[name="question_type"]');
    let initial = {};
    try {
      const node = document.getElementById('qb-initial-item');
      if (node) initial = JSON.parse(node.dataset.initialItem);
    } catch (_) {
      form.addEventListener('submit', e => { if (type.value === 'fill_gaps') e.preventDefault(); });
      panel.hidden = false; status.textContent = window.SchoolMonitorI18n.t("qb_d68c84f1d211");
      return;
    }
    if (!rich || typeof rich.init !== 'function' || typeof rich.sync !== 'function') {
      if (attempts++ < 100) { setTimeout(init, 50); return; }
      panel.hidden = false; status.textContent = window.SchoolMonitorI18n.t("qb_5702a62c4019");
      form.addEventListener('submit', e => {
        if (type.value === 'fill_gaps' && group.querySelector('[name="fill_gaps_mode"]:checked')?.value === 'word_bank') e.preventDefault();
      });
      return;
    }
    group.dataset.richBankReady = '1';
    const source = group.querySelector('[name="fill_gaps_text"]');
    const introduction = group.querySelector('.qb-answer-builder__header p');
    const originalIntroduction = introduction?.textContent;
    const sourceLabel=group.querySelector('label[for="fill_gaps_text"]'),originalSourceLabel=sourceLabel?.textContent;
    const originalPlaceholder=source.placeholder;
    const list = group.querySelector('[data-rich-bank-rows]');
    const payload = group.querySelector('[data-rich-bank-payload]');
    const score = (window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]'));
    const modes = [...group.querySelectorAll('[name="fill_gaps_mode"]')];
    const legacy = initial.question_type === 'fill_gaps' && initial.grading_settings?.fill_gaps_score_policy !== 'per_gap_v1';
    let seeded = false, lastBank = false, counter = 0, textSnapshot = null;
    const rows = [];
    const matches = () => [...source.value.matchAll(/\[\[([^\[\]\r\n]+)]]/g)];
    const active = () => !legacy && type.value === 'fill_gaps' && modes.find(r => r.checked)?.value === 'word_bank';
    function gapCount() { return matches().length; }
    const ui = JSON.parse(panel.dataset.fgLabels);
    const alphabet = 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ';
    function letter(index) {let n=index+1, value='';while(n>0){n--;value=alphabet[n%alphabet.length]+value;n=Math.floor(n/alphabet.length);}return value;}
    let building = false;
    function bankSegments(row) {
      const editor=row.querySelector('[data-rich-editor]'); rich.sync(editor);
      return JSON.parse(editor.querySelector('[data-rich-segments]').value || '[]');
    }
    function renderSegments(target, segments) {
      for(const segment of segments) {
        if(segment.type==='latex') {
          const field=document.createElement('math-field');field.setAttribute('read-only','');field.setAttribute('math-virtual-keyboard-policy','manual');field.tabIndex=-1;field.textContent=segment.text;target.append(field);
        } else if(segment.type==='image') {
          const img=document.createElement('img');img.src=panel.dataset.fgMediaUrl+'?object_key='+encodeURIComponent(segment.object_key);img.alt=segment.alt||'';img.style.cssText='max-width:100%;max-height:120px;object-fit:contain';target.append(img);
        } else target.append(document.createTextNode(segment.text || ''));
      }
    }
    function renderSelections() {
      if(building)return;
      const holder=panel.querySelector('[data-fg-pickers]');
      const open=new Set([...holder.querySelectorAll('details[open]')].map(node=>node.dataset.gap));
      const focus=document.activeElement?.dataset.fgChoice;
      holder.replaceChildren();
      const bank=rows.map(row=>({row,segments:bankSegments(row)}));
      rows.forEach((row,index)=>{
        row.querySelector('[data-bank-label]').textContent=ui.variant+' '+letter(index);
        const accepted=[...row.bankAccepted].filter(id=>Number(id.slice(1))<=gapCount()).map(id=>Number(id.slice(1))+')');
        row.querySelector('[data-bank-gaps]').textContent=accepted.length?ui.correct+': '+accepted.join(', '):ui.distractor;
      });
      for(let index=1;index<=gapCount();index++) {
        const id='G'+index, details=document.createElement('details'), summary=document.createElement('summary');
        details.className='qb-fg-picker';details.dataset.gap=id;details.open=open.has(id);
        const number=document.createElement('strong');number.textContent=index+')';summary.append(number);
        const chosen=bank.filter(item=>item.row.bankAccepted.has(id));
        if(!chosen.length)summary.append(document.createTextNode(ui.choose));
        chosen.forEach((item,i)=>{if(i)summary.append(document.createTextNode(' / '));renderSegments(summary,item.segments);});
        details.append(summary);
        bank.forEach((item,position)=>{
          const label=document.createElement('label'), check=document.createElement('input'), body=document.createElement('span');
          label.className='qb-fg-option';check.type='checkbox';check.checked=item.row.bankAccepted.has(id);check.dataset.fgChoice=id+':'+item.row.dataset.value;
          const marker=document.createElement('strong');marker.textContent=letter(position);body.append(marker,document.createTextNode(' · '));renderSegments(body,item.segments);
          check.addEventListener('change',()=>{if(check.checked)item.row.bankAccepted.add(id);else item.row.bankAccepted.delete(id);renderSelections();});
          label.append(check,body);details.append(label);
        });
        holder.append(details);
      }
      const preview=panel.querySelector('[data-fg-filled]');preview.replaceChildren();let offset=0;
      matches().forEach((match,index)=>{
        preview.append(document.createTextNode(source.value.slice(offset,match.index)));
        const selected=bank.find(item=>item.row.bankAccepted.has('G'+(index+1)));
        const answer=document.createElement('span');answer.style.cssText='background:#dcfce7;padding:2px 5px;border-radius:4px;';
        if(selected)renderSegments(answer,selected.segments);else answer.textContent=(index+1)+') '+ui.missing;
        preview.append(answer);offset=match.index+match[0].length;
      });
      preview.append(document.createTextNode(source.value.slice(offset)));
      if(focus)[...holder.querySelectorAll('[data-fg-choice]')].find(node=>node.dataset.fgChoice===focus)?.focus({preventScroll:true});
    }
    function updateChecks() {renderSelections();}
    function add(item = null, accepted = []) {
      const fragment = group.querySelector('[data-rich-bank-template]').content.cloneNode(true);
      const row = fragment.querySelector('[data-rich-bank-row]');
      row.dataset.value = item?.value || `W${++counter}`;
      counter = Math.max(counter, Number(row.dataset.value.slice(1)) || 0);
      row.bankAccepted = new Set(accepted);
      row.querySelector('[data-bank-label]').textContent = row.dataset.value;
      const editor = row.querySelector('[data-rich-editor]');
      editor.dataset.initialSegments = JSON.stringify(item?.segments || []);
      list.append(row); rows.push(row); rich.init(editor); updateChecks(row);
      const symbols = document.createElement('div');
      for (const symbol of ['∈', '∉', '⊂', '⊆', '∪', '∩', '∅', '≤', '≥', '≠']) {
        const button = document.createElement('button');
        button.type = 'button'; button.textContent = symbol; button.setAttribute('aria-label', window.SchoolMonitorI18n.t("qb_06d2b12ea0f9", {p0: (symbol)}));
        button.addEventListener('mousedown', event => event.preventDefault());
        button.addEventListener('click', () => {
          const content = editor.querySelector('[data-rich-content]'), selection = window.getSelection();
          if (selection?.rangeCount && content.contains(selection.anchorNode) && content.contains(selection.focusNode)) {
            const range = selection.getRangeAt(0); range.deleteContents();
            const node = document.createTextNode(symbol); range.insertNode(node); range.setStartAfter(node); range.collapse(true);
            selection.removeAllRanges(); selection.addRange(range);
          } else content.append(document.createTextNode(symbol));
          content.focus(); content.dispatchEvent(new Event('input', {bubbles: true})); rich.sync(editor);
        });
        symbols.append(button);
      }
      editor.querySelector('.qb-rich-editor__toolbar').append(symbols);
      row.querySelector('[data-bank-remove]').addEventListener('click', () => {
        rows.splice(rows.indexOf(row), 1); row.remove();renderSelections();
      });
      return row;
    }
    function seed() {
      if (seeded) return;
      seeded = true; building = true;
      if (initial.question_type === 'fill_gaps' && initial.content?.word_bank_format === 'rich_v1') {
        for (const item of initial.content.word_bank) {
          const accepted = Object.entries(initial.answer_key.gaps)
            .filter(([, gap]) => gap.accepted_answers.includes(item.value)).map(([id]) => id);
          add(item, accepted);
        }
      } else {
        const byText = new Map();
        function answer(text, gap) {
          if (!text) return;
          let row = byText.get(text);
          if (!row) { row = add({value: `W${++counter}`, segments: [{type: 'text', text}]}); byText.set(text, row); }
          if (gap) row.bankAccepted.add(gap);
        }
        matches().forEach((m, index) => {
          const id = `G${index + 1}`; answer(m[1].trim(), id);
          group.querySelectorAll(`[name="fill_gap_alternatives_${id}"]`).forEach(input => answer(input.value.trim(), id));
        });
        const bank = initial.question_type === 'fill_gaps' ? initial.content?.word_bank : null;
        if (Array.isArray(bank)) bank.forEach(value => { if (typeof value === 'string') answer(value); });
        group.querySelectorAll('[name="fill_word_bank"]').forEach(input => answer(input.value.trim()));
      }
      if (!rows.length) add();
      building = false; renderSelections();
    }
    function serialize() {
      const segments = [], gaps = {}, found = matches(); let cursor = 0;
      found.forEach((match, index) => {
        if (match.index > cursor) segments.push({type: 'text', text: source.value.slice(cursor, match.index)});
        const id = `G${index + 1}`; segments.push({type: 'gap', gap_id: id});
        gaps[id] = {accepted_answers: rows.filter(row => row.bankAccepted.has(id)).map(row => row.dataset.value)};
        cursor = match.index + match[0].length;
      });
      if (cursor < source.value.length) segments.push({type: 'text', text: source.value.slice(cursor)});
      const bank = rows.map(row => {
        const editor = row.querySelector('[data-rich-editor]'); rich.sync(editor);
        return {value: row.dataset.value, segments: JSON.parse(editor.querySelector('[data-rich-segments]').value || '[]')};
      });
      if (!found.length || found.length !== Number(score.value)) throw new Error(window.SchoolMonitorI18n.t("qb_fd6876623d17"));
      if (!bank.length || bank.some(item => !item.segments.length)) throw new Error(window.SchoolMonitorI18n.t("qb_9591c81493e0"));
      if (bank.length > 300) throw new Error(window.SchoolMonitorI18n.t("qb_15b41ba7431e"));
      const signatures = bank.map(item => JSON.stringify(item.segments.map(s => [s.type, s.text.trim()])));
      if (new Set(signatures).size !== signatures.length) throw new Error(window.SchoolMonitorI18n.t("qb_856e38c88340"));
      if (Object.values(gaps).some(gap => !gap.accepted_answers.length)) throw new Error(window.SchoolMonitorI18n.t("qb_18461f8dca35"));
      return {content: {input_mode: 'word_bank', word_bank_format: 'rich_v1', segments, word_bank: bank}, answer_key: {gaps}};
    }
    function toTextMode() {
      const data = serialize(), byId = new Map(data.content.word_bank.map(item => [item.value, item]));
      const primary = {}, alternatives = {};
      for (const [id, gap] of Object.entries(data.answer_key.gaps)) {
        const values = gap.accepted_answers.map(value => byId.get(value).segments.map(s => s.text).join(''));
        if (values.some(v => !v.trim() || /[\[\]\r\n]/.test(v))) throw new Error(window.SchoolMonitorI18n.t("qb_d42c590b06a0"));
        primary[id] = values[0]; alternatives[id] = values.slice(1);
      }
      let i = 0; source.value = source.value.replace(/\[\[([^\[\]\r\n]+)]]/g, () => `[[${primary[`G${++i}`]}]]`);
      source.dispatchEvent(new Event('input', {bubbles: true}));
      for (const [id, values] of Object.entries(alternatives)) {
        const target = group.querySelector(`[data-fill-gap-card][data-gap-id="${id}"] [data-fill-alternatives]`);
        if (!target && values.length) throw new Error(window.SchoolMonitorI18n.t("qb_cb12d7562e71"));
        if (target) {
          target.replaceChildren();
          values.forEach(value => { const input = document.createElement('input'); input.type = 'text'; input.name = `fill_gap_alternatives_${id}`; input.value = value; input.className = 'qb-form-control'; input.setAttribute('data-type-input', ''); target.append(input); });
        }
      }
      textSnapshot = source.value;
    }
    function refresh() {
      let enabled = active();
      if (lastBank && !enabled && type.value === 'fill_gaps') {
        try { toTextMode(); }
        catch (error) {
          modes.forEach(r => r.checked = r.value === 'word_bank'); enabled = true;
          status.textContent = error.message;
        }
      }
      if (enabled) {
        seed();
        // Text-mode edits are authoritative on return; preserve rich expressions
        // whose serialized text still matches instead of flattening every row.
        if (!lastBank && textSnapshot !== null && source.value !== textSnapshot) {
          const byText = new Map();
          rows.forEach(row => {
            const editor = row.querySelector('[data-rich-editor]'); rich.sync(editor);
            const segments = JSON.parse(editor.querySelector('[data-rich-segments]').value || '[]');
            byText.set(segments.map(s => s.text).join(''), row); row.bankAccepted.clear();
          });
          function accept(text, id) {
            if (!text) return;
            let row = byText.get(text);
            if (!row) { row = add({value: `W${++counter}`, segments: [{type: 'text', text}]}); byText.set(text, row); }
            row.bankAccepted.add(id);
          }
          matches().forEach((match, index) => {
            const id = `G${index + 1}`; accept(match[1].trim(), id);
            group.querySelectorAll(`[name="fill_gap_alternatives_${id}"]`).forEach(input => accept(input.value.trim(), id));
          });
        }
        if (!lastBank) {
          let index = 0;
          source.value = source.value.replace(/\[\[([^\[\]\r\n]+)]]/g, () => `[[${++index}]]`);
          source.dispatchEvent(new Event('input', {bubbles: true}));
        }
      }
      if (introduction) introduction.textContent = enabled
        ? ui.instruction
        : originalIntroduction;
      if(sourceLabel)sourceLabel.textContent=enabled ? ui.instruction : originalSourceLabel;
      source.placeholder=enabled ? '… [[1]] … [[2]] …' : originalPlaceholder;
      panel.hidden = !enabled; group.dataset.richBankActive = String(enabled);
      payload.disabled = !enabled; if (!enabled) payload.value = '';
      if (enabled) {
        renderSelections();
        group.querySelectorAll('#fill-gaps-settings input, #fill-word-bank-section input').forEach(input => input.disabled = true);
      }
      lastBank = enabled;
    }
    group.querySelector('[data-rich-bank-add]').addEventListener('click', () => add());
    source.addEventListener('input', () => { if (active()) renderSelections(); });
    let previewTimer;
    group.addEventListener('input',event=>{if(active() && event.target.closest('[data-rich-editor]')){clearTimeout(previewTimer);previewTimer=setTimeout(renderSelections,150);}});
    modes.forEach(radio => radio.addEventListener('change', refresh));
    type.addEventListener('change', refresh);
    form.addEventListener('submit', event => {
      if (!active()) return;
      try { payload.disabled = false; payload.value = JSON.stringify(serialize()); status.textContent = ''; }
      catch (error) { event.preventDefault(); status.textContent = error.message; }
    }, true);
    refresh();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => setTimeout(init, 0));
  else setTimeout(init, 0);
})();
