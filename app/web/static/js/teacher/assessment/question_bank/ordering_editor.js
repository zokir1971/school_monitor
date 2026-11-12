/* One point per correct position; legacy create.js stays intact. */
(() => {
  let attempts=0;
  function init(){
    const group=document.getElementById('ordering-fields');
    if(!group || group.dataset.scoredOrderingReady)return;
    const form=group.closest('form'),type=form.querySelector('[name="question_type"]'),score=(window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]'));
    const status=group.querySelector('[data-scored-ordering-status]');
    let initial={};
    try{const source=document.getElementById('qb-initial-item');if(source)initial=JSON.parse(source.dataset.initialItem);}
    catch(error){status.textContent=window.SchoolMonitorI18n.t("qb_eb5a04324d8e");form.addEventListener('submit',e=>{if(type.value==='ordering')e.preventDefault();});return;}
    const legacy=initial.question_type==='ordering' && initial.grading_settings?.ordering_score_policy!=='per_position_v1';
    const rich=window.QuestionRichEditor;
    if(!legacy && (!rich || typeof rich.init!=='function' || typeof rich.sync!=='function')){
      if(attempts++<100){setTimeout(init,50);return;}
      status.textContent=window.SchoolMonitorI18n.t("qb_f83dbe83a4fc");form.addEventListener('submit',e=>{if(type.value==='ordering')e.preventDefault();});return;
    }
    const legacyBox=group.querySelector('[data-ordering-legacy]'),list=group.querySelector('[data-scored-ordering-rows]'),payload=group.querySelector('[data-scored-ordering-payload]');
    const rows=[],displayOrder=[];
    group.querySelector('.qb-answer-builder__header p').textContent=legacy
      ?window.SchoolMonitorI18n.t("qb_eb2e1168de82")
      :window.SchoolMonitorI18n.t("qb_545a983d1134");
    function add(item=null){
      const fragment=group.querySelector('[data-scored-ordering-template]').content.cloneNode(true),row=fragment.querySelector('[data-scored-ordering-row]');
      let id=item?.value;if(!id){let n=rows.length+1;while(rows.some(r=>r.dataset.id===`I${n}`))n++;id=`I${n}`;}
      row.dataset.id=id;if(!displayOrder.includes(id))displayOrder.push(id);
      const editor=row.querySelector('[data-rich-editor]');editor.dataset.initialSegments=JSON.stringify(item?.segments||[]);
      const content=editor.querySelector('[data-rich-content]');content.id=`scored-ordering-item-${id}`;row.querySelector('[data-scored-ordering-label]').htmlFor=content.id;
      list.append(row);rows.push(row);rich.init(editor);
    }
    try{
      if(!legacy && initial.question_type==='ordering'){
        const items=initial.content.items,order=initial.answer_key.order;displayOrder.push(...items.map(item=>item.value));
        const byId=new Map(items.map(item=>[item.value,item]));
        if(order.length!==items.length || new Set(order).size!==order.length)throw new Error('Invalid order');
        order.forEach(id=>{const item=byId.get(id);if(!item)throw new Error('Missing item');add(item);});
      }
    }catch(error){status.textContent=window.SchoolMonitorI18n.t("qb_dda90104f738");form.addEventListener('submit',e=>{if(type.value==='ordering')e.preventDefault();});return;}
    group.dataset.scoredOrderingReady='1';
    function count(){const n=Number(score.value);return Number.isInteger(n)&&n>=2&&n<=100?n:null;}
    function refresh(){
      const active=type.value==='ordering';legacyBox.hidden=!legacy;list.hidden=legacy;payload.disabled=!active||legacy;
      legacyBox.querySelectorAll('input').forEach(input=>{input.disabled=!active||!legacy;input.required=active&&legacy&&input.name==='ordering_item';});
      if(legacy)return;
      const n=count();if(active)score.setCustomValidity(n?'':window.SchoolMonitorI18n.t("qb_94ae888105ac"));
      while(active&&n&&rows.length<n)add();
      rows.forEach((row,index)=>{
        const visible=n!==null&&index<n;row.hidden=!visible;row.querySelector('[data-scored-ordering-label]').textContent=window.SchoolMonitorI18n.t("qb_99eed55589ed", {p0: (index+1)});
        row.querySelectorAll('input').forEach(input=>input.disabled=!active||!visible);row.querySelector('[data-rich-content]').contentEditable=String(active&&visible);
        row.querySelector('[data-ordering-move="-1"]').disabled=!active||!visible||index===0;
        row.querySelector('[data-ordering-move="1"]').disabled=!active||!visible||index===n-1;
        list.append(row);
      });
      status.textContent=n?window.SchoolMonitorI18n.t("qb_6a504f252440", {p0: (n)})+(rows.length>n?window.SchoolMonitorI18n.t("qb_775d1271418f"):''):window.SchoolMonitorI18n.t("qb_96572504604a");
      if(active && n && window.QBAuthoringScore?.help(form))status.textContent=window.QBAuthoringScore.help(form);
    }
    list.addEventListener('click',event=>{
      const button=event.target.closest?.('[data-ordering-move]');if(!button||button.disabled)return;
      const index=rows.indexOf(button.closest('[data-scored-ordering-row]')),target=index+Number(button.dataset.orderingMove),n=count();
      if(index<0||!n||target<0||target>=n)return;
      const [row]=rows.splice(index,1);rows.splice(target,0,row);refresh();button.focus();
    });
    score.addEventListener('input',refresh);score.addEventListener('change',refresh);type.addEventListener('change',refresh);
    form.addEventListener('submit',event=>{
      if(type.value!=='ordering'||legacy)return;
      refresh();const n=count();if(!n){event.preventDefault();score.reportValidity();return;}
      const byId=new Map(),order=[];
      for(const row of rows.slice(0,n)){
        const editor=row.querySelector('[data-rich-editor]');rich.sync(editor);const segments=JSON.parse(editor.querySelector('[data-rich-segments]').value||'[]');
        if(!segments.length){event.preventDefault();status.textContent=window.SchoolMonitorI18n.t("qb_4709e54e361e");editor.querySelector('[data-rich-content]').focus();return;}
        byId.set(row.dataset.id,{value:row.dataset.id,segments});order.push(row.dataset.id);
      }
      const items=displayOrder.filter(id=>byId.has(id)).map(id=>byId.get(id));payload.value=JSON.stringify({items,order});
    },true);
    refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,0));else setTimeout(init,0);
})();
