/* Scored matching adapter; legacy matching/create.js remain compatible. */
(() => {
  let attempts = 0;
  function init() {
    const group = document.getElementById('matching-fields');
    if (!group || group.dataset.scoredMatchingReady) return;
    const form = group.closest('form');
    const type = form.querySelector('[name="question_type"]');
    const score = (window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]'));
    const status = group.querySelector('[data-scored-matching-status]');
    let initial = {};
    try {
      const source = document.getElementById('qb-initial-item');
      if (source) initial = JSON.parse(source.dataset.initialItem);
    } catch (error) {
      status.textContent = window.SchoolMonitorI18n.t("qb_eb5a04324d8e");
      form.addEventListener('submit', event => { if (type.value === 'matching') event.preventDefault(); });
      return;
    }
    const legacy = initial.question_type === 'matching' && initial.grading_settings?.matching_score_policy !== 'per_pair_v1';
    const rich = window.QuestionRichEditor;
    if (!legacy && (!rich || typeof rich.init !== 'function' || typeof rich.sync !== 'function')) {
      if (attempts++ < 100) { setTimeout(init,50); return; }
      status.textContent = window.SchoolMonitorI18n.t("qb_a64ebcbd68ef");
      form.addEventListener('submit', event => { if (type.value === 'matching') event.preventDefault(); });
      return;
    }
    const legacyBox = group.querySelector('[data-matching-legacy]');
    const list = group.querySelector('[data-scored-matching-rows]');
    const payload = group.querySelector('[data-scored-matching-payload]');
    const rows = [], rightOrder = [];
    group.querySelector('.qb-answer-builder__header p').textContent = legacy
      ? window.SchoolMonitorI18n.t("qb_829744fdc86c")
      : window.SchoolMonitorI18n.t("qb_3c0b1d92e4cb");
    const alphabet = 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ';
    function letter(index) {let n=index+1, result='';while(n>0){n--;result=alphabet[n%alphabet.length]+result;n=Math.floor(n/alphabet.length);}return result;}
    function add(left = null,right = null) {
      const fragment = group.querySelector('[data-scored-matching-template]').content.cloneNode(true);
      const row = fragment.querySelector('[data-scored-matching-row]');
      function identifier(prefix,field) { let n = rows.length+1; while(rows.some(r => r.dataset[field] === `${prefix}${n}`)) n++;return `${prefix}${n}`; }
      row.dataset.leftId = left?.value || identifier('L','leftId');
      row.dataset.rightId = right?.value || identifier('R','rightId');
      if (!rightOrder.includes(row.dataset.rightId)) rightOrder.push(row.dataset.rightId);
      row.querySelector('[data-scored-matching-label]').textContent = `${rows.length+1})`;
      list.append(row); rows.push(row);
      for (const side of ['left','right']) {
        const editor = row.querySelector(`[data-matching-side="${side}"]`);
        editor.dataset.initialSegments = JSON.stringify((side === 'left' ? left : right)?.segments || []);
        const content = editor.querySelector('[data-rich-content]');content.id = `scored-matching-${rows.length}-${side}`;
        row.querySelector(`[data-matching-editor-label="${side}"]`).htmlFor = content.id;
        const label = row.querySelector(`[data-matching-editor-label="${side}"]`);
        const mark = side === 'left' ? String(rows.length) : letter(rightOrder.indexOf(row.dataset.rightId));
        label.dataset.baseLabel = label.textContent;
        label.textContent = `${label.dataset.baseLabel} (${mark})`;
        rich.init(editor);
      }
    }
    try {
      if (!legacy && initial.question_type === 'matching') {
        const left = initial.content.left, right = initial.content.right;
        rightOrder.push(...right.map(item => item.value));
        const rightById = new Map(right.map(item => [item.value,item]));
        const pairs = new Map(initial.answer_key.pairs.map(pair => [pair.left,pair.right]));
        left.forEach(item => {
          const match = rightById.get(pairs.get(item.value));
          if (!match) throw new Error('Missing matching pair');
          add(item,match);
        });
      }
    } catch (error) {
      status.textContent = window.SchoolMonitorI18n.t("qb_c2b8b51c0ca0");
      form.addEventListener('submit',event => { if(type.value === 'matching')event.preventDefault(); });return;
    }
    group.dataset.scoredMatchingReady = '1';
    function count(){const n = Number(score.value);return Number.isInteger(n) && n >= 2 && n <= 100 ? n : null;}
    function refresh(){
      const active = type.value === 'matching';
      legacyBox.hidden = !legacy;
      legacyBox.querySelectorAll('input').forEach(input=>{input.disabled = !active || !legacy;input.required = active && legacy && ['matching_left','matching_right'].includes(input.name);});
      list.hidden = legacy;payload.disabled = !active || legacy;
      if(legacy)return;
      const n = count();
      if(active)score.setCustomValidity(n ? '' : window.SchoolMonitorI18n.t("qb_66b2e6545283"));
      while(active && n && rows.length < n)add();
      const visibleRight = new Set(rows.slice(0,n || 0).map(row=>row.dataset.rightId));
      const orderedRight = rightOrder.filter(id=>visibleRight.has(id));
      rows.forEach((row,index)=>{
        const visible = n !== null && index < n;row.hidden = !visible;
        for (const side of ['left','right']) {
          const label=row.querySelector(`[data-matching-editor-label="${side}"]`);
          const mark=side==='left' ? String(index+1) : letter(orderedRight.indexOf(row.dataset.rightId));
          if(visible)label.textContent=`${label.dataset.baseLabel} (${mark})`;
        }
        row.querySelectorAll('input').forEach(input=>input.disabled = !active || !visible);
        row.querySelectorAll('[data-rich-content]').forEach(content=>content.contentEditable=String(active && visible));
      });
      status.textContent = n ? window.SchoolMonitorI18n.t("qb_4a47985b9732", {p0: (n)})+(rows.length>n?window.SchoolMonitorI18n.t("qb_632127a79f0d"):'') : window.SchoolMonitorI18n.t("qb_5334eec100e0");
      if(active && n && window.QBAuthoringScore?.help(form))status.textContent=window.QBAuthoringScore.help(form);
    }
    score.addEventListener('input',refresh);score.addEventListener('change',refresh);type.addEventListener('change',refresh);
    form.addEventListener('submit',event=>{
      if(type.value !== 'matching' || legacy)return;
      refresh();const n=count();if(!n){event.preventDefault();score.reportValidity();return;}
      const left=[],rightById=new Map(),pairs=[];
      for(const row of rows.slice(0,n)){
        const parts={};
        for(const side of ['left','right']){
          const editor=row.querySelector(`[data-matching-side="${side}"]`);rich.sync(editor);
          const segments=JSON.parse(editor.querySelector('[data-rich-segments]').value || '[]');
          if(!segments.length){event.preventDefault();status.textContent=window.SchoolMonitorI18n.t("qb_e659b3523297");editor.querySelector('[data-rich-content]').focus();return;}
          parts[side]={value:row.dataset[side+'Id'],segments};
        }
        left.push(parts.left);rightById.set(parts.right.value,parts.right);pairs.push({left:parts.left.value,right:parts.right.value});
      }
      const right=rightOrder.filter(id=>rightById.has(id)).map(id=>rightById.get(id));
      payload.value=JSON.stringify({left,right,pairs});
    },true);
    refresh();
  }
  if(document.readyState === 'loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,0));else setTimeout(init,0);
})();
