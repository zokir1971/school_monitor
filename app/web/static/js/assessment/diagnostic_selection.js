(() => {
 'use strict';
 // School options are already scoped to the plan by the server; no extra requests.
 const geography=document.querySelector('[data-diagnostic-filter]');
 if(geography){
  const district=geography.querySelector('[data-geography="district"]');
  const school=geography.querySelector('[data-geography="school"]');
  if(school){
   const options=Array.from(school.options);
   function refreshSchools(reset){
    const chosen=reset?'':school.value,districtID=district?.value||'';
    const visible=options.filter(option=>!option.value||!districtID||option.dataset.districtId===districtID);
    for(const option of visible){
     option.hidden=false;option.disabled=false;
     if(option.value)option.textContent=(districtID?'':option.dataset.districtName+' · ')+option.dataset.schoolName;
    }
    school.replaceChildren(...visible);
    school.value=visible.some(option=>option.value===chosen)?chosen:'';
   }
   refreshSchools(false);
   geography.addEventListener('change',event=>{
    const kind=event.target.name==='plan_id'?'region':event.target.dataset.geography;
    if(kind==='region'&&district&&!district.disabled)district.value='';
    if(kind==='region'||kind==='district')refreshSchools(true);
   });
  }
 }
 const form=document.querySelector('[data-diagnostic-create]');if(!form)return;
 const ru=form.dataset.language==='ru',say=(r,k)=>ru?r:k;
 const key='sm:diagnostic-create:v97:'+form.dataset.key;
 const boxes=Array.from(form.querySelectorAll('input[type="checkbox"][name="class_ids"]'));
 const plans=Array.from(form.querySelectorAll('input[type="checkbox"][name="plan_ids"]'));
 const master=form.querySelector('[data-select-visible]'),clear=form.querySelector('[data-clear-classes]');
 const count=form.querySelector('[data-selection-count]'),error=form.querySelector('[data-selection-error]');
 const allFiltered=form.querySelector('[data-select-filtered]');
 const total=Number(form.dataset.total||0),filterSignature=form.dataset.filter;
 const simple=['title_ru','title_kk','opens_at','closes_at','request_key'];
 const isID=v=>typeof v==='string'&&/^[1-9][0-9]{0,9}$/.test(v);
 let selected=new Set(JSON.parse(form.dataset.selected||'[]').map(String).filter(isID));
 function limit(){error.textContent=say('Можно выбрать не более 5000 классов. Снимите лишние отметки или сузьте фильтр.','5000 сыныптан артық таңдауға болмайды. Артық белгілерді алып тастаңыз немесе сүзгіні тарылтыңыз.');}
 function sync(){if(allFiltered.checked)return;for(const box of boxes)box.checked?selected.add(box.value):selected.delete(box.value);}
 function draw(){
  for(const box of boxes)box.disabled=allFiltered.checked;master.disabled=allFiltered.checked||boxes.length===0;
  let visible=0;for(const box of boxes){box.checked=allFiltered.checked||selected.has(box.value);if(box.checked)visible++;}
  master.checked=boxes.length>0&&visible===boxes.length;master.indeterminate=visible>0&&visible<boxes.length;
  if(allFiltered.checked){count.textContent=say('По фильтру выбрано классов: ','Сүзгі бойынша таңдалған сыныптар: ')+total+' / 5000';return;}
  count.textContent=say('Выбрано классов: ','Таңдалған сыныптар: ')+selected.size+' / 5000'+(selected.size>visible?say(' · На других страницах/фильтрах: ',' · Басқа беттерде/сүзгілерде: ')+(selected.size-visible):'');
 }
 function draft(){
  const data={filtered:allFiltered.checked,filter:filterSignature,classes:Array.from(selected),plans:plans.filter(b=>b.checked).map(b=>b.value),fields:{},minutes:{}};
  for(const name of simple){const el=form.elements.namedItem(name);if(el)data.fields[name]=el.value;}
  for(const el of form.querySelectorAll('input[name^="minutes_"]'))data.minutes[el.name]=el.value;
  return data;
 }
 function store(){
  try{sessionStorage.setItem(key,JSON.stringify(draft()));}
  catch(e){if(!error.textContent)error.textContent=say('Браузер запретил сохранение выбора между страницами. Не переключайте фильтры до отправки.','Браузер беттер арасында таңдауды сақтауға рұқсат бермеді. Жібергенге дейін сүзгілерді ауыстырмаңыз.');}
 }
 if(form.dataset.posted!=='1'){
  try{
   const d=JSON.parse(sessionStorage.getItem(key)||'null');
   if(d&&Array.isArray(d.classes)&&d.classes.length<=5000&&d.classes.every(isID)){
    selected=new Set(d.classes);
    allFiltered.checked=d.filtered===true&&d.filter===filterSignature;
    if(Array.isArray(d.plans))for(const box of plans)box.checked=d.plans.includes(box.value);
    for(const name of simple){const el=form.elements.namedItem(name);const value=d.fields?.[name];if(el&&typeof value==='string'&&value.length<=255)el.value=value;}
    for(const el of form.querySelectorAll('input[name^="minutes_"]')){const v=d.minutes?.[el.name];if(typeof v==='string'&&/^[0-9]{1,3}$/.test(v))el.value=v;}
   }
  }catch(e){/* Malformed or unavailable tab storage never changes server authorization. */}
 }
 function changed(){error.textContent='';sync();draw();store();}
 for(const box of boxes)box.addEventListener('change',()=>{
  if(box.checked&&!selected.has(box.value)&&selected.size>=5000){box.checked=false;limit();draw();return;}
  changed();
 });
 master.addEventListener('change',()=>{
  if(master.checked){
   const all=new Set([...selected,...boxes.map(b=>b.value)]);
   if(all.size>5000){limit();draw();return;}
   selected=all;
  }else for(const box of boxes)selected.delete(box.value);
  error.textContent='';draw();store();
 });
 clear.addEventListener('click',()=>{selected.clear();allFiltered.checked=false;error.textContent='';draw();store();});
 allFiltered.addEventListener('change',()=>{if(allFiltered.checked&&(total===0||total>5000)){allFiltered.checked=false;if(total===0)error.textContent=say('Нет классов по текущему фильтру.','Ағымдағы сүзгі бойынша сыныптар жоқ.');else limit();}else error.textContent='';draw();store();});
 form.addEventListener('input',store);
 form.addEventListener('change',store);
 form.addEventListener('submit',event=>{
  sync();draw();
  if(!allFiltered.checked&&selected.size===0){event.preventDefault();error.textContent=say('Выберите хотя бы один класс.','Кемінде бір сыныпты таңдаңыз.');return;}
  if((!allFiltered.checked&&selected.size>5000)||(allFiltered.checked&&(total<1||total>5000))){event.preventDefault();limit();return;}
  const hidden=form.querySelector('[data-hidden-classes]');hidden.replaceChildren();
  const onPage=new Set(boxes.filter(b=>b.checked).map(b=>b.value));
  for(const id of selected)if(!allFiltered.checked&&!onPage.has(id)){
   const input=document.createElement('input');input.type='hidden';input.name='class_ids';input.value=id;hidden.appendChild(input);
  }
  store();
 });
 const filter=document.querySelector('[data-diagnostic-filter]');
 if(filter){
  filter.addEventListener('submit',store);
  filter.addEventListener('change',event=>{
   const kind=event.target.name==='plan_id'?'region':event.target.dataset.geography;
   if(kind==='region'){
    const district=filter.querySelector('[data-geography="district"]');if(district&&!district.disabled)district.value='';
   }
   if(kind==='region'||kind==='district'){
    const school=filter.querySelector('[data-geography="school"]');if(school)school.value='';
   }
  });
 }
 for(const link of document.querySelectorAll('[data-class-page]'))link.addEventListener('click',store);
 window.addEventListener('pagehide',store);
 draw();if(selected.size>5000)limit();store();
})();
