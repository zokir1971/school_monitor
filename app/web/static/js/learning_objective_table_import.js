(() => {
'use strict';
const initialNode=document.getElementById('lo-initial-rows');
if(!initialNode)return;
const initial=JSON.parse(initialNode.value);
const settings=JSON.parse(document.getElementById('lo-selected-pages').value);
const container=document.getElementById('lo-rows');
const skills = [
  ['', '—'],
  ['listening', window.SchoolMonitorI18n.t("ed_9ccd023aaac0")],
  ['speaking', window.SchoolMonitorI18n.t("ed_955e655c3a92")],
  ['reading', window.SchoolMonitorI18n.t("ed_629923f4bab3")],
  ['writing', window.SchoolMonitorI18n.t("ed_138cdc285e8b")],
  ['listening_speaking', window.SchoolMonitorI18n.t("ed_89acf8b7dfca")],
  ['language_norms', window.SchoolMonitorI18n.t("ed_984ce1d1c738")],
  ['language_skills', window.SchoolMonitorI18n.t("ed_414b74a90fdf")],
];
const multiple=settings.multiple_quarters===true;
const sourceNode=document.getElementById('lo-source-rows');
const sourceRows=sourceNode?JSON.parse(sourceNode.value):initial;
const sourceQuarters=new Map();
sourceRows.forEach((row,index)=>sourceQuarters.set(String(row.import_row_id??index), new Set((row.quarters||[]).map(Number))));
const selectedQuarters=card=>[...card.querySelectorAll('[data-quarter]:checked')].map(x=>Number(x.dataset.quarter));
const formatQuarters=values=>[...values].sort((a,b)=>a-b).join(', ')||'—';
function originalQuarters(card){
 return sourceQuarters.get(card.dataset.importRowId);
}
function updateQuarterNote(card){
 const note=card.querySelector('[data-quarter-note]');if(!note)return;
 const original=originalQuarters(card),current=selectedQuarters(card);
 const changed=original&&formatQuarters(original)!==formatQuarters(current);
 note.textContent=original?window.SchoolMonitorI18n.t("ed_67e769b0ca2f")+formatQuarters(original)+(changed?window.SchoolMonitorI18n.t("ed_16504e5099d8")+formatQuarters(current):window.SchoolMonitorI18n.t("ed_7b4c138b0080")):window.SchoolMonitorI18n.t("ed_04613a394eaa");
 note.style.color=changed?'#a53b12':'';
}
function refreshPreview(){
 const filter=Number(document.getElementById('lo-quarter-filter')?.value||0);
 const counts=[1,2,3,4].map(q=>{
  const codes=new Set();
  for(const card of container.children){if(selectedQuarters(card).includes(q))codes.add(card.querySelector('[data-key="code"]').value.trim());}
  return q+': '+codes.size;
 });
 for(const card of container.children){card.hidden=Boolean(filter&&!selectedQuarters(card).includes(filter));updateQuarterNote(card);}
 const summary=document.getElementById('lo-quarter-summary');if(summary)summary.textContent=window.SchoolMonitorI18n.t("ed_77554c8396cf")+counts.join(' · ');
 count();
}
document.getElementById('lo-quarter-filter')?.addEventListener('change',refreshPreview);
function field(parent,label,key,value,type='text') {
 const wrap=document.createElement('label');wrap.textContent=label;
 const input=document.createElement(type==='textarea'?'textarea':type==='select'?'select':'input');input.dataset.key=key;
 if(type==='select'){
  const options=key==='language_skill'?skills:[['',window.SchoolMonitorI18n.t("ed_6a323db2ae5b")],...[1,2,3,4].map(x=>[String(x),String(x)])];
  for(const [v,t] of options){const o=document.createElement('option');o.value=v;o.textContent=t;input.append(o);}
 }else if(type!=='textarea')input.type=type;
 input.value=value??'';input.required=['code','grade_level','quarter'].includes(key);
 if(key==='grade_level'){input.min=settings.grade_from;input.max=settings.grade_to;}
 wrap.append(input);parent.append(wrap);return input;
}
function check(parent,label,key,value){
 const wrap=document.createElement('label');wrap.className='lo-check';
 const input=document.createElement('input');input.type='checkbox';input.dataset.key=key;input.checked=value===true;
 wrap.append(input,document.createTextNode(label));parent.append(wrap);return input;
}
function rich(parent,language,row){
 const box=document.createElement('section');box.className='lo-language';
 const heading=document.createElement('h3');heading.textContent=language==='kz'?window.SchoolMonitorI18n.t("ed_f9a1b8f74637"):window.SchoolMonitorI18n.t("ed_8b41c8a54b47");box.append(heading);
 const editor=document.createElement('div');editor.dataset.richEditor='';editor.dataset.language=language;editor.className='qb-rich-editor';
 const segments=row['title_segments_'+language]??(row['title_'+language]?[{type:'text',text:row['title_'+language]}]:[]);
 editor.dataset.initialSegments=JSON.stringify(segments);
 const tools=document.createElement('div');tools.className='lo-rich-tools';
 for(const [attr,label] of [['add-math',window.SchoolMonitorI18n.t("ed_204b50701760")],['edit-math',window.SchoolMonitorI18n.t("ed_e5918f24f2b9")],['copy-math',window.SchoolMonitorI18n.t("ed_b06f90a3236b")],['paste-math',window.SchoolMonitorI18n.t("ed_26fb5703246a")],['delete-math',window.SchoolMonitorI18n.t("ed_ea8f1bacce63")]]){
  const b=document.createElement('button');b.type='button';b.dataset['rich'+attr.split('-').map(x=>x[0].toUpperCase()+x.slice(1)).join('')]='';b.textContent=label;tools.append(b);
 }
 const content=document.createElement('div');content.dataset.richContent='';content.className='qb-rich-editor__content';content.contentEditable='true';content.setAttribute('role','textbox');content.setAttribute('aria-label',heading.textContent);content.setAttribute('aria-multiline','true');
 const hidden=document.createElement('input');hidden.type='hidden';hidden.dataset.richSegments='';hidden.value=JSON.stringify(segments);
 const plain=document.createElement('input');plain.type='hidden';plain.dataset.richPlainValue='';
 editor.append(tools,content,hidden,plain);box.append(editor);
 const flag=check(box,window.SchoolMonitorI18n.t("ed_1ab457c0ea95"),'has_formula_'+language,row['has_formula_'+language]===true||segments.some(x=>x.type==='latex'));
 const reviewed=check(box,window.SchoolMonitorI18n.t("ed_7d88daed5ad3"),'formula_reviewed_'+language,row['formula_reviewed_'+language]);
 const toggle=()=>{reviewed.disabled=!flag.checked;if(!flag.checked)reviewed.checked=false;};flag.addEventListener('change',()=>{reviewed.checked=false;toggle();});toggle();
 if(row['formula_suspected_'+language]){const note=document.createElement('p');note.className='lo-warning';note.textContent=window.SchoolMonitorI18n.t("ed_55b38cc2e9fa");box.append(note);}
 let previous=JSON.stringify(segments);
 editor.addEventListener('objective:rich-sync',event=>{
  const now=JSON.stringify(event.detail);
  if(now!==previous){reviewed.checked=false;previous=now;}
  if(event.detail.some(x=>x.type==='latex'))flag.checked=true;
  toggle();
 });
 parent.append(box);
 if(window.ObjectiveRichEditor)window.ObjectiveRichEditor.init(editor);
}
function add(row={}){
 const card=document.createElement('section');card.className='lo-row';if(row.import_row_id!==undefined)card.dataset.importRowId=String(row.import_row_id);
 const top=document.createElement('div');top.className='lo-row-top';
 field(top,window.SchoolMonitorI18n.t("ed_ab850b5faf2d"),'grade_level',row.grade_level??settings.grade_from,'number');field(top,window.SchoolMonitorI18n.t("ed_1a0f527018fa"),'code',row.code??settings.fixed_code);
 if(settings.fixed_code){top.querySelector('[data-key="code"]').readOnly=true;top.querySelector('[data-key="grade_level"]').readOnly=true;}
 if(multiple){
  const qs=document.createElement('fieldset');const legend=document.createElement('legend');legend.textContent=window.SchoolMonitorI18n.t("ed_50e3d96ce3f9");qs.append(legend);
  for(const q of [1,2,3,4]){const l=document.createElement('label');const c=document.createElement('input');c.type='checkbox';c.dataset.quarter=String(q);c.checked=(row.quarters||[]).includes(q);l.append(c,document.createTextNode(String(q)));qs.append(l);}top.append(qs);
  const note=document.createElement('p');note.dataset.quarterNote='';top.append(note);
  const restore=document.createElement('button');restore.type='button';restore.className='lo-button lo-secondary';restore.textContent=window.SchoolMonitorI18n.t("ed_7d6b6483a126");
  restore.addEventListener('click',()=>{const original=originalQuarters(card);if(!original){alert(window.SchoolMonitorI18n.t("ed_ee5961db0514"));return;}for(const c of card.querySelectorAll('[data-quarter]'))c.checked=original.has(Number(c.dataset.quarter));refreshPreview();});top.append(restore);
 }else field(top,window.SchoolMonitorI18n.t("ed_d90a39723aaf"),'quarter',row.quarter,'select');
 if(row.quarter_conflict){const note=document.createElement('p');note.className='lo-error';note.textContent=window.SchoolMonitorI18n.t("ed_b19d6f82f149");top.append(note);}
 field(top,window.SchoolMonitorI18n.t("ed_7aecf79ee8bd"),'language_skill',row.language_skill,'select');
 const remove=document.createElement('button');remove.type='button';remove.className='lo-button lo-danger';remove.textContent=window.SchoolMonitorI18n.t("ed_d6e61de8581e");remove.addEventListener('click',()=>{card.remove();refreshPreview();});top.append(remove);card.append(top);
 const texts=document.createElement('div');texts.className='lo-texts';card.append(texts);
 const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent=window.SchoolMonitorI18n.t("ed_a68a1c70d894");details.append(summary);
 const grid=document.createElement('div');grid.className='lo-grid';
 for(const [key,label] of [['section_code',window.SchoolMonitorI18n.t("ed_2c7e2adc6d6d")],['subsection_code',window.SchoolMonitorI18n.t("ed_622034407750")],['section_title_kz',window.SchoolMonitorI18n.t("ed_7837cfaabdfe")],['section_title_ru',window.SchoolMonitorI18n.t("ed_cd1e55ed10eb")],['subsection_title_kz',window.SchoolMonitorI18n.t("ed_a6c2e12af62e")],['subsection_title_ru',window.SchoolMonitorI18n.t("ed_c934ca010ad1")]])field(grid,label,key,row[key]);
 for(const lang of ['kz','ru']){
  if(!multiple)field(grid,window.SchoolMonitorI18n.t("ed_01eda5fd1b6c")+lang.toUpperCase(),'source_pages_'+lang,(row['source_pages_'+lang]||[]).join(','));
  const locations=row['source_cells_'+lang]||[];
  if(locations.length){const raw=document.createElement('pre');raw.style.whiteSpace='pre-wrap';raw.textContent=locations.map(x=>x.sheet+'!'+x.cell+'\n'+x.raw).join('\n\n');grid.append(raw);}
  if(locations.length){const text=document.createElement('p');text.textContent=lang.toUpperCase()+': '+locations.map(x=>x.sheet+'!'+x.cell).join(', ');grid.append(text);}
 }
 details.append(grid);card.append(details);container.append(card);
 rich(texts,'kz',row);rich(texts,'ru',row);card.addEventListener('change',refreshPreview);refreshPreview();
}
function count(){const cards=[...container.children];const codes=new Set(cards.map(card=>card.querySelector('[data-key="code"]').value.trim()).filter(Boolean));document.getElementById('lo-count').textContent=window.SchoolMonitorI18n.t("ed_3ae0fd5ae8ff")+codes.size+window.SchoolMonitorI18n.t("ed_12e8d2ec49d0")+cards.length+window.SchoolMonitorI18n.t("ed_ebc22f9e5408")+cards.filter(card=>!card.hidden).length;}
initial.forEach((row,index)=>add({...row,import_row_id:row.import_row_id??String(index)}));
document.getElementById('lo-add').addEventListener('click',()=>add());
document.getElementById('lo-confirm').addEventListener('submit',event=>{
 try{
  if(!window.ObjectiveRichEditor)throw new Error(window.SchoolMonitorI18n.t("ed_d7e58b39f2e6"));
  const changes=[];
  if(multiple){for(const card of container.children){const original=originalQuarters(card);if(original&&formatQuarters(original)!==formatQuarters(selectedQuarters(card)))changes.push(card.querySelector('[data-key="code"]').value+window.SchoolMonitorI18n.t("ed_b0bd0a9e9f31")+(card.dataset.importRowId??window.SchoolMonitorI18n.t("ed_da0a315913ce"))+'): '+formatQuarters(original)+' → '+formatQuarters(selectedQuarters(card)));}}
  const activeIds=new Set([...container.children].map(card=>card.dataset.importRowId));
  sourceRows.forEach((row,index)=>{if(!activeIds.has(String(row.import_row_id??index)))changes.push(row.code+window.SchoolMonitorI18n.t("ed_b0bd0a9e9f31")+(row.import_row_id??index)+window.SchoolMonitorI18n.t("ed_494b84cdad1f"));});
  if(changes.length&&!window.confirm(window.SchoolMonitorI18n.t("ed_3ec5d45f14b2")+changes.join('\n')+window.SchoolMonitorI18n.t("ed_abe31093977e"))){event.preventDefault();return;}
  const rows=[];
  for(const card of container.children){
   const row={};if(card.dataset.importRowId!==undefined)row.import_row_id=card.dataset.importRowId;
   if(multiple){row.quarters=[...card.querySelectorAll('[data-quarter]:checked')].map(x=>Number(x.dataset.quarter));if(!row.quarters.length)throw new Error(window.SchoolMonitorI18n.t("ed_37c5a9f449d6"));}
   for(const input of card.querySelectorAll('[data-key]')){
    const key=input.dataset.key;
    if(input.type==='checkbox')row[key]=input.checked;
    else if(['grade_level','quarter'].includes(key))row[key]=Number(input.value);
    else if(key.startsWith('source_pages_')){
     if(input.value.trim()&&!/^\s*\d+(\s*,\s*\d+)*\s*$/.test(input.value))throw new Error(window.SchoolMonitorI18n.t("ed_9c1c3fa13a08"));
     row[key]=input.value.trim()?input.value.split(',').map(Number):[];
    }else row[key]=input.value.trim();
   }
   for(const editor of card.querySelectorAll('[data-rich-editor]')){
    window.ObjectiveRichEditor.sync(editor);
    const lang=editor.dataset.language,segments=JSON.parse(editor.querySelector('[data-rich-segments]').value||'[]');
    row['title_segments_'+lang]=segments;
    row['title_'+lang]=segments.map(s=>s.type==='text'?s.text:'$$'+s.text+'$$').join('').trim();
    row['has_formula_'+lang]=card.querySelector(`[data-key="has_formula_${lang}"]`).checked;
    row['formula_reviewed_'+lang]=card.querySelector(`[data-key="formula_reviewed_${lang}"]`).checked;
    const latex=segments.some(s=>s.type==='latex');
    if(row['has_formula_'+lang]&&(!latex||!row['formula_reviewed_'+lang]))throw new Error(window.SchoolMonitorI18n.t("ed_dce18995865f", {p0: (row.code), p1: (lang.toUpperCase())}));
   }
   if(!row.title_kz&&!row.title_ru)throw new Error(window.SchoolMonitorI18n.t("ed_d9168f488917", {p0: (row.code)}));
   rows.push(row);
  }
  document.getElementById('lo-rows-json').value=JSON.stringify(rows);
 }catch(error){event.preventDefault();alert(error.message);}
});
})();
