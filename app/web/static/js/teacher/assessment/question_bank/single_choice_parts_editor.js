/* Shared rich editors; no duplicated math toolbar implementation. */
(() => {
  let attempts=0;
  function init() {
    const group=document.getElementById('single-choice-fields');
    if(!group||group.dataset.scReady) return;
    const rich=window.QuestionRichEditor;
    if(!rich&&attempts++<100) {setTimeout(init,50);return;}
    const form=group.closest('form'),type=form.querySelector('[name="question_type"]'),score=(window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]'));
    const list=group.querySelector('[data-sc-parts]'),old=group.querySelector('[data-sc-legacy]'),payload=group.querySelector('[data-sc-payload]'),status=group.querySelector('[data-sc-status]');
    let initial={};
    try {const item=document.getElementById('qb-initial-item');if(item) initial=JSON.parse(item.dataset.initialItem);}
    catch(_) {status.textContent=group.dataset.scInvalid;form.addEventListener('submit',e=>e.preventDefault());return;}
    const legacy=initial.question_type==='single_choice'&&!Array.isArray(initial.content?.parts);
    group.dataset.scReady='1';group.dataset.scMultipart=legacy?'0':'1';
    const rows=[];
    function add(part=null,answer='') {
      const fragment=group.querySelector('[data-sc-part-template]').content.cloneNode(true);
      const row=fragment.querySelector('[data-sc-part]');
      let identifier=part?.id;
      if(!identifier) {let n=rows.length+1;while(rows.some(r=>r.dataset.id===`P${n}`))n++;identifier=`P${n}`;}
      row.dataset.id=identifier;row.querySelector('[data-sc-label]').textContent=`${rows.length+1})`;
      const editors=[...row.querySelectorAll('[data-rich-editor]')];
      const values=[part?.segments||[],...['A','B','C','D'].map(value=>(part?.options||[]).find(o=>o.value===value)?.segments||[])];
      editors.forEach((editor,index)=>{editor.dataset.initialSegments=JSON.stringify(values[index]);editor.querySelector('[data-rich-content]').setAttribute('aria-label',`${group.dataset.scPartLabel} ${rows.length+1} / ${index?['A','B','C','D'][index-1]:'…'}`);});
      row.querySelector('[data-sc-answer]').value=answer;
      list.append(row);rows.push(row);editors.forEach(editor=>rich.init(editor));
    }
    if(!legacy&&rich&&initial.question_type==='single_choice') (initial.content.parts||[]).forEach(part=>add(part,initial.answer_key?.values?.[part.id]||''));
    function count() {const n=Number(score.value);return Number.isInteger(n)&&n>=1&&n<=100?n:null;}
    function refresh() {
      const active=type.value==='single_choice';
      old.hidden=!legacy;list.hidden=legacy;payload.disabled=!active||legacy;
      old.querySelectorAll('input').forEach(input=>{input.disabled=!active||!legacy;input.required=active&&legacy&&input.type==='radio';});
      if(legacy) return;
      const n=count();score.setCustomValidity(active&&!n?group.dataset.scInvalid:'');
      if(rich&&active) while(n&&rows.length<n) add();
      rows.forEach((row,index)=>{
        const shown=n!==null&&index<n;row.hidden=!shown;
        row.querySelectorAll('input,select').forEach(input=>input.disabled=!active||!shown);
        row.querySelector('[data-sc-answer]').required=active&&shown;
        row.querySelectorAll('[data-rich-content]').forEach(node=>node.contentEditable=String(active&&shown));
      });
      status.textContent=window.QBAuthoringScore?.help(form) || group.dataset.scCountHelp;
    }
    score.addEventListener('input',refresh);score.addEventListener('change',refresh);type.addEventListener('change',refresh);
    form.addEventListener('submit',event=>{
      if(type.value!=='single_choice'||legacy)return;
      refresh();const n=count();
      if(!n||!rich){event.preventDefault();status.textContent=group.dataset.scInvalid;return;}
      const parts=[],values={};
      for(const row of rows.slice(0,n)) {
        const editors=[...row.querySelectorAll('[data-rich-editor]')];
        editors.forEach(editor=>rich.sync(editor));
        const segments=editors.map(editor=>JSON.parse(editor.querySelector('[data-rich-segments]').value||'[]'));
        const answer=row.querySelector('[data-sc-answer]').value;
        if(segments.some(items=>!items.length)||!answer) {event.preventDefault();status.textContent=group.dataset.scInvalid;row.scrollIntoView({block:'center'});return;}
        parts.push({id:row.dataset.id,segments:segments[0],options:['A','B','C','D'].map((value,index)=>({value,segments:segments[index+1]}))});
        values[row.dataset.id]=answer;
      }
      payload.value=JSON.stringify({parts,values});
    },true);
    refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,0));else setTimeout(init,0);
})();
