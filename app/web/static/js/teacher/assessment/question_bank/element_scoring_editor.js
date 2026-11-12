/* v2 is opt-in for new records; old saved records keep their original controls. */
(() => {
 const api={help(form){return form.querySelector('[data-element-scoring]')?.dataset.countHelp || '';},countInput(form){return form.querySelector('[name="element_count"]')||form.querySelector('[name="max_score"]')}};
 window.QBAuthoringScore=api;
 function init(){
  const box=document.querySelector('[data-element-scoring]');if(!box)return;
  const form=box.closest('form'),type=form.querySelector('[name="question_type"]'),count=box.querySelector('[name="element_count"]'),points=box.querySelector('[name="points_per_element"]'),correct=box.querySelector('[name="correct_option_count"]'),criteria=box.querySelector('[name="criterion_points"]'),maximum=form.querySelector('[name="max_score"]'),rules=JSON.parse(box.dataset.rules);
  if(box.dataset.locked==='1')box.querySelectorAll('input').forEach(input=>input.readOnly=true);
  let lastType=type.value;
  function update(){
   const rule=rules[type.value];if(!rule)return;
   const changedType=type.value!==lastType;
   if(changedType){count.value=rule.min_elements;lastType=type.value;}
   count.min=rule.min_elements;count.max=rule.max_elements;points.min=1;points.max=rule.max_points;
   const manual=type.value==='manual_review';
   box.querySelector('[data-correct-count]').hidden=type.value!=='multiple_choice';correct.disabled=type.value!=='multiple_choice';
   box.querySelector('[data-criteria-points]').hidden=!manual;criteria.disabled=!manual;
   points.closest('label').hidden=manual;
   const values=criteria.value.split(',').map(v=>Number(v.trim())),n=Number(count.value),p=Number(points.value);
   const valid=Number.isInteger(n)&&n>=rule.min_elements&&n<=rule.max_elements&&Number.isInteger(p)&&p>=1&&p<=100;
   maximum.readOnly=true;
   maximum.value=manual?values.reduce((sum,v)=>sum+v,0):n*p;
   count.setCustomValidity(valid?'':box.dataset.error);
   if(manual)criteria.setCustomValidity(values.length===n&&values.every(v=>Number.isInteger(v)&&v>0&&v<=100)?'':box.dataset.error);
   if(!manual)criteria.setCustomValidity('');
   maximum.dispatchEvent(new Event('input',{bubbles:true}));
   if(changedType)count.dispatchEvent(new Event('change',{bubbles:true}));
  }
  count.addEventListener('input',update);points.addEventListener('input',update);criteria.addEventListener('input',update);type.addEventListener('change',update);correct.addEventListener('input',update);
  form.addEventListener('submit',()=>update(),true);
  update();
  // Fill new manual criteria from the explicit plan, preserving authored text on edit.
  if(type.value==='manual_review'){
   const group=document.getElementById('manual-review-fields'),weights=criteria.value.split(',').map(Number);
   if(group){const list=group.querySelector('[data-manual-criteria]');let guard=0;
    while(list && list.children.length<weights.length && guard++<50)group.querySelector('[data-manual-add]').click();
    [...group.querySelectorAll('[name="manual_criterion_score"]')].forEach((input,i)=>{if(weights[i])input.value=weights[i];if(box.dataset.locked==='1')input.readOnly=true;});
    group.dispatchEvent(new Event('input',{bubbles:true}));
    if(box.dataset.locked!=='1'){
      criteria.readOnly=true;count.readOnly=true;
      function syncCriteria(){
       const inputs=[...group.querySelectorAll('[name="manual_criterion_score"]')];
       count.value=inputs.length;criteria.value=inputs.map(input=>input.value).join(',');update();
      }
      group.addEventListener('input',event=>{if(event.target.name==='manual_criterion_score')syncCriteria();});
      group.addEventListener('click',event=>{if(event.target.closest('button'))setTimeout(syncCriteria,0);});
    }
   }
  }
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,0));else setTimeout(init,0);
})();
