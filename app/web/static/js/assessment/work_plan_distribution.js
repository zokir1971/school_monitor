(() => {
 'use strict';
 const form=document.querySelector('[data-distribution-form]'),root=document.querySelector('[data-work-selection-root]');if(!form||!root)return;
 const key=`work-plan-selection:v101:${root.dataset.user}:${root.dataset.plan}:${form.dataset.choiceContext}`;
 let saved={};try{if(form.dataset.posted!=='1')saved=JSON.parse(sessionStorage.getItem(key)||'{}');}catch{}
 const rows=[...form.querySelectorAll('[data-distribution-row]')];
 const store=()=>{
  const values={};for(const row of rows){
   for(const select of row.querySelectorAll('[data-variant-choice]'))values[select.name]=select.value;}
  try{sessionStorage.setItem(key,JSON.stringify(values));}catch{}
 };
 const unused=()=>{
  let selected=[];try{selected=JSON.parse(form.dataset.selectedPool||'[]').map(String);}catch{}
  const used=new Set();for(const row of rows){const common=row.querySelector('[data-common-choice]');
   for(const col of row.querySelectorAll('[data-choice-column]')){const select=col.querySelector('[data-variant-choice]');const id=common.checked?row.dataset.seed:(select?select.value:col.dataset.staticChoice);if(id)used.add(id);}}
  const missing=selected.filter(id=>!used.has(id));const note=form.querySelector('[data-unused-note]'),span=form.querySelector('[data-unused-cards]');
  if(note&&span){note.hidden=!missing.length;span.textContent=missing.map(id=>'№'+id).join(', ');}
 };
 for(const row of rows){
  const common=row.querySelector('[data-common-choice]');
  for(const select of row.querySelectorAll('[data-variant-choice]'))if(saved[select.name]&&[...select.options].some(o=>o.value===saved[select.name]))select.value=saved[select.name];
  // Common is accepted only from server state or a fresh user checkbox action, never tab storage.
  const update=()=>{
   for(const select of row.querySelectorAll('[data-variant-choice]')){select.disabled=common.checked;select.hidden=common.checked;select.required=!common.checked;}
   for(const el of row.querySelectorAll('[data-common-placeholder]'))el.hidden=!common.checked;
   const warning=row.querySelector('[data-common-warning]');if(warning)warning.hidden=!common.checked;
   for(const col of row.querySelectorAll('[data-choice-column]')){
    const select=col.querySelector('[data-variant-choice]'),id=common.checked?row.dataset.seed:(select?select.value:col.dataset.staticChoice);
    const preview=col.querySelector('[data-choice-preview]'),source=document.getElementById('work-choice-'+id);
    if(preview){preview.replaceChildren();if(source)preview.append(source.content.cloneNode(true));}
   }
   const error=form.querySelector('[data-distribution-error]');if(error)error.hidden=true;
   unused();store();
  };
  common.addEventListener('change',update);for(const select of row.querySelectorAll('[data-variant-choice]'))select.addEventListener('change',update);update();
 }
 form.addEventListener('submit',event=>{
  const used=new Set();let duplicate=false;
  for(const row of rows){
   const common=row.querySelector('[data-common-choice]'),inRow=[];
   for(const col of row.querySelectorAll('[data-choice-column]')){const select=col.querySelector('[data-variant-choice]'),id=common.checked?row.dataset.seed:(select?select.value:col.dataset.staticChoice);if(id)inRow.push(id);}
   const unique=new Set(inRow);if(!common.checked&&unique.size!==inRow.length)duplicate=true;
   for(const id of unique){if(used.has(id))duplicate=true;used.add(id);}
  }
  if(duplicate){event.preventDefault();const error=form.querySelector('[data-distribution-error]');error.textContent=form.dataset.duplicateMessage;error.hidden=false;error.scrollIntoView({block:'center'});}
 });
 unused();
})();
