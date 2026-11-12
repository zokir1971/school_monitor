(() => {
 function init(){document.querySelectorAll('[data-creation-plan]').forEach(root=>{
  if(root.dataset.ready)return;root.dataset.ready='1';
  const form=root.closest('form'),list=root.querySelector('[data-plan-rows]'),hidden=root.querySelector('[data-plan-value]'),total=root.querySelector('[data-plan-total]'),error=root.querySelector('[data-plan-error]'),rules=JSON.parse(root.dataset.rules),labels=JSON.parse(root.dataset.labels);
  const rows=()=>[...list.children],field=(row,key)=>row.querySelector('[data-plan-'+key+']');
  function refresh(){
   let cards=0,units=0,scoreTotal=0,valid=true;const messages=[];
   const plan=rows().map((row,index)=>{
    const kind=field(row,'type').value,rule=rules[kind],manual=kind==='manual_review';
    const count=Number(field(row,'count').value),n=Number(field(row,'elements').value),points=Number(field(row,'points').value),correct=Number(field(row,'correct').value);
    field(row,'elements').min=rule.min_elements;field(row,'elements').max=rule.max_elements;
    field(row,'criteria').closest('label').hidden=!manual;field(row,'correct').closest('label').hidden=kind!=='multiple_choice';field(row,'points').closest('label').hidden=manual;
    const weights=field(row,'criteria').value.split(',').map(v=>Number(v.trim()));
    const maximum=manual?weights.reduce((a,b)=>a+b,0):n*points;field(row,'score').value=Number.isFinite(maximum)?maximum:0;
    const issues=[];
    function check(key,ok,requirement){const input=field(row,key);input.setCustomValidity?.(ok?'':requirement);input.setAttribute?.('aria-invalid',ok?'false':'true');if(!ok)issues.push(requirement);}
    check('count',Number.isInteger(count)&&count>=1&&count<=10,labels.cards+': 1–10');
    check('elements',Number.isInteger(n)&&n>=rule.min_elements&&n<=rule.max_elements,labels.elements+': '+rule.min_elements+'–'+rule.max_elements);
    check('points',manual||(Number.isInteger(points)&&points>=1&&points<=100),labels.points+': 1–100');
    check('criteria',!manual||(weights.length===n&&weights.every(v=>Number.isInteger(v)&&v>=1&&v<=100)),labels.criteria+': '+n+' × (1–100)');
    check('correct',kind!=='multiple_choice'||[2,3].includes(correct),labels.correct+': 2–3');
    if(issues.length){valid=false;messages.push(`${index+1}) ${field(row,'type').selectedOptions[0]?.textContent}: ${issues.join('; ')}`);}
    cards+=count;units+=count*n;scoreTotal+=count*maximum;
    field(row,'row-summary').textContent=`${index+1}) ${field(row,'type').selectedOptions[0]?.textContent} · ${field(row,'difficulty').selectedOptions[0]?.textContent}: ${manual?count+' × ('+weights.join('+')+')':count+' × '+n+' × '+points} · ${labels.total}: ${count*maximum}`;
    field(row,'remove').disabled=rows().length===1;
    const result={question_type:kind,difficulty:field(row,'difficulty').value,count,element_score_policy:'weighted_elements_v2',element_count:n,points_per_element:points,max_score:String(maximum)};
    if(manual)result.criterion_points=weights;
    if(kind==='multiple_choice'){result.option_count=4;result.correct_option_count=correct;}
    return result;
   });
   if(!Number.isFinite(cards)||cards<1||cards>10){valid=false;messages.push(labels.cards+' 1–10');}
   if(root.dataset.ai==='1'&&units>32){valid=false;messages.push(labels.budget);}
   hidden.value=JSON.stringify(plan);total.textContent=`${labels.cards}: ${cards} · ${labels.elements}: ${units} · ${labels.total}: ${scoreTotal}`;
   error.textContent=messages.join('\n');error.style.whiteSpace='pre-line';error.hidden=valid;root.querySelector('[data-plan-add]').disabled=cards>=10;
   return valid;
  }
  function add(value={}){
   const row=root.querySelector('template').content.firstElementChild.cloneNode(true);list.append(row);
   field(row,'type').value=value.question_type||'single_choice';field(row,'difficulty').value=value.difficulty||'basic';field(row,'count').value=value.count??1;
   const kind=field(row,'type').value,old=value.max_score?Number(value.max_score):1;
   field(row,'elements').value=value.element_count??(['short_text','multiple_choice','image_choice','manual_review'].includes(kind)?1:old);
   field(row,'points').value=value.points_per_element??(['short_text','multiple_choice','image_choice'].includes(kind)?old:1);
   field(row,'correct').value=value.correct_option_count??(kind==='multiple_choice'&&[2,3].includes(old)?old:2);
   field(row,'criteria').value=(value.criterion_points||[old]).join(',');
   field(row,'remove').addEventListener('click',()=>{if(rows().length>1)row.remove();refresh();});
   field(row,'type').addEventListener('change',()=>{const rule=rules[field(row,'type').value];field(row,'elements').value=rule.min_elements;refresh();});
   refresh();
  }
  let initial;try{initial=JSON.parse(hidden.value);}catch{};(Array.isArray(initial)&&initial.length?initial:[{}]).forEach(add);
  root.addEventListener('input',refresh);root.addEventListener('change',refresh);root.querySelector('[data-plan-add]').addEventListener('click',()=>{if(rows().length<10)add();});
  form.addEventListener('submit',event=>{if(!refresh()){event.preventDefault();event.stopImmediatePropagation();error.scrollIntoView({block:'center'});}},true);
 });}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
