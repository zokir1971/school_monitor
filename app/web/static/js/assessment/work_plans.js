document.querySelectorAll('[data-work-plan-form]').forEach(form=>{
  const field=name=>form.elements.namedItem(name);
  function update(){
    const policy=field('language_policy').value;
    ['kk','ru'].forEach(language=>{
      const title=field('title_'+language);
      if(title)title.required=policy==='auto'||policy==='both'||policy===language;
    });
    const baseline=field('work_type').value==='baseline';
    const grade=Number(field('participant_grade').value);
    const curriculum=grade?(baseline?grade-1:grade):0;
    form.querySelector('[data-curriculum-grade]').value=curriculum>0?String(curriculum):'—';
    const show=(selector,visible,name)=>{form.querySelector(selector).hidden=!visible;field(name).disabled=!visible;};
    show('[data-quarter]',!baseline,'quarter');
    show('[data-track]',curriculum===10||curriculum===11,'education_track');
    field('education_track').required=curriculum===10||curriculum===11;
    show('[data-source-subject]',baseline,'curriculum_subject_id');
  }
  form.addEventListener('change',update);update();
});
