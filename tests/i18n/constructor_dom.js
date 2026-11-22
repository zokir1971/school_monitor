/* Minimal DOM for constructor tests. No browser, network, storage or real forms. */
const fs=require('fs'),vm=require('vm');
const args=JSON.parse(fs.readFileSync(0,'utf8'));
const decode=s=>String(s).replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
class El {
 constructor(className=''){this.className=className;this.children=[];this.events={};this.dataset={};this.value='';this.checked=false;}
 appendChild(child){child.parent=this;this.children.push(child);return child;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
 addEventListener(name,f){this.events[name]=f;}
 all(){return this.children.flatMap(c=>[c,...c.all()]);}
 querySelectorAll(q){
  if(q.startsWith('.'))return this.all().filter(c=>c.className.split(' ').includes(q.slice(1)));
  const m=q.match(/^\[name="(.+)"\]$/);if(m)return this.all().filter(c=>c.name===m[1]);
  throw Error('Unsupported element selector '+q);
 }
 querySelector(q){return this.querySelectorAll(q)[0]||null;}
 set innerHTML(html){
  this.html=html;this.children=[];
  if(this.className==='template-section'){
   const input=this.appendChild(new El('section-title'));
   input.value=decode(html.match(/class="section-title"[^>]*value="([^"]*)"/s)[1]);
   this.appendChild(new El('criteria-list'));this.appendChild(new El('add-criterion-btn'));this.appendChild(new El('remove-section-btn'));
  }else if(this.className==='criterion-row'){
   const input=this.appendChild(new El('criterion-input'));
   input.value=decode(html.match(/class="criterion-input"[^>]*value="([^"]*)"/s)[1]);
   this.appendChild(new El('remove-criterion-btn'));
  }else if(this.className==='criteria-section'){
   for(const match of html.matchAll(/<input\b([^>]*)>/gs)){
    const attrs=Object.fromEntries([...match[1].matchAll(/([\w-]+)="([^"]*)"/g)].map(m=>[m[1],decode(m[2])]));
    const input=this.appendChild(new El());Object.assign(input,attrs);
   }
  }
 }
}
const ids={};for(const id of ['sections-container','add-section-btn','lesson-template-form','schema_json','max_score','show_total_score','criteria-list','templateConstructorForm'])ids[id]=new El();
ids.show_total_score.checked=true;
const infos=(args.mode==='lesson'?['teacher_name','teacher_post','subject','organization','class_group','controller_name','controller_post','lesson_datetime','theme','learning_objectives']:args.info_fields).map(value=>Object.assign(new El('info-field'),{value,checked:true}));
if(args.mode==='notebook'){
 args.criteria.forEach((c,i)=>{
  const section=ids['criteria-list'].appendChild(new El('criteria-section'));section.dataset.index=String(i);
  for(const[key,value]of Object.entries({key:c.key,label_kz:c.label_kz,score_2_kz:c.scores['2'].label_kz,score_1_kz:c.scores['1'].label_kz,score_0_kz:c.scores['0'].label_kz})){
   const field=section.appendChild(new El());field.name=`criteria[${i}][${key}]`;field.value=value;
  }
 });
}
const doc={getElementById(id){return ids[id]},createElement(){return new El()},querySelector(q){const m=q.match(/^\.info-field\[value="(.+)"\]$/);return m?infos.find(x=>x.value===m[1]):null},querySelectorAll(q){
 if(q==='.info-field')return infos;if(q==='.info-field:checked'||q==='input[name="info_fields"]:checked')return infos.filter(x=>x.checked);
 if(q==='.template-section')return ids['sections-container'].children;
 if(q==='.criterion-input')return ids['sections-container'].querySelectorAll(q);
 if(q==='.criteria-section')return ids['criteria-list'].children;
 throw Error('Unsupported document selector '+q);
}};
const window={existingSchema:args.schema,SchoolMonitorI18n:{t(k,values={}){const text=args.messages[k]??k;return text.replace(/\{(p\d+)\}/g,(m,n)=>n in values?String(values[n]):m)}}};
const sandbox={document:doc,window};vm.createContext(sandbox);vm.runInContext(args.script,sandbox);
if(args.mode==='lesson'){
 const submit=()=>{ids['lesson-template-form'].events.submit();return JSON.parse(ids.schema_json.value)};
 const first=submit();
 const firstMax=ids.max_score.value;
 ids['add-section-btn'].events.click();
 const added=ids['sections-container'].children.at(-1);
 added.querySelector('.section-title').value='NEW SECTION';added.querySelector('.criterion-input').value='NEW CRITERION';
 const afterAdd=submit();
 const original=ids['sections-container'].children[0];original.querySelectorAll('.remove-criterion-btn')[0].events.click();
 const afterRemove=submit();added.querySelector('.remove-section-btn').events.click();const afterSectionRemove=submit();
 process.stdout.write(JSON.stringify({first,firstMax,afterAdd,afterRemove,afterSectionRemove,existing:window.existingSchema}));
}else{
 const submit=()=>{ids.templateConstructorForm.events.submit();return JSON.parse(ids.schema_json.value)};
 const first=submit();ids['criteria-list'].children[0].remove();sandbox.addNotebookCriterion();
 const newRow=ids['criteria-list'].children.at(-1);newRow.querySelector(`[name="criteria[${newRow.dataset.index}][label_kz]"]`).value='NEW NOTEBOOK CRITERION';
 const afterEdit=submit();process.stdout.write(JSON.stringify({first,afterEdit,addedHtml:ids['criteria-list'].children.at(-1).html}));
}
