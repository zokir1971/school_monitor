(() => {
 function init(){
  const form=document.querySelector('.qb-catalog-filter form');if(!form)return;
  const subject=form.querySelector('#catalog-subject'),grade=form.querySelector('#catalog-grade'),track=form.querySelector('#catalog-track'),quarter=form.querySelector('#catalog-quarter'),objective=form.querySelector('#catalog-objective');
  if(!subject||!grade||!track||!quarter||!objective)return;
  const submit=()=>{window.SchoolAssessmentUI?.remember(form);form.submit();};
  const reset=fields=>fields.forEach(input=>{input.value='';input.disabled=true;});
  subject.addEventListener('change',()=>{reset([grade,track,quarter,objective]);submit();});
  grade.addEventListener('change',()=>{reset([track,quarter,objective]);submit();});
  track.addEventListener('change',()=>{reset([objective]);submit();});
  quarter.addEventListener('change',()=>{reset([objective]);submit();});
  objective.addEventListener('change',()=>submit());
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
