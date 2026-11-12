(() => {
 const type=document.getElementById('assessment_type'),mode=document.getElementById('assessment_mode'),quarter=document.getElementById('naming_quarter'),checkpoint=document.getElementById('checkpoint');
 if(!type||!mode||!quarter)return;
 const ru=document.documentElement.lang!=='kk';
 const note=document.createElement('p');note.className='form-help';note.setAttribute('aria-live','polite');mode.parentElement.appendChild(note);
 const caption=mode.parentElement.querySelector('label');if(caption)caption.textContent=ru?'Ввод результатов':'Нәтижелерді енгізу';
 function sync(){
  const baseline=type.value==='baseline',summative=['sor','soch'].includes(type.value);
  quarter.disabled=baseline;quarter.required=summative;quarter.parentElement.hidden=baseline;
  const number=document.getElementById('section_number');if(number){number.disabled=type.value!=='sor';number.parentElement.hidden=type.value!=='sor';}
  if(summative&&mode.value!=='by_objectives'){mode.value='by_objectives';mode.dispatchEvent(new Event('change',{bubbles:true}));}
  mode.querySelector('option[value="without_objectives"]').disabled=summative;
  if(checkpoint){
   for(const option of checkpoint.options){const q=option.value.startsWith('quarter_');option.disabled=(baseline&&q)||(!baseline&&option.value==='baseline');}
   if(checkpoint.selectedOptions[0]?.disabled)checkpoint.value='';
  }
  const grades=[...new Set([...document.querySelectorAll('input[name="school_class_ids"]:checked')].map(c=>Number(c.dataset.gradeLevel)).filter(Boolean))];
  const program=grades.length===1 ? (baseline?grades[0]-1:grades[0]):null;
  note.textContent=(program ? (ru?'Проверяемая программа: ':'Тексерілетін бағдарлама: ')+program+(ru?' класс. ':' сынып. '):'')+(baseline?(ru?'Проверяется программа предыдущего класса. Можно ввести только общий балл или выбрать учебные цели предыдущего класса.':'Алдыңғы сынып бағдарламасы тексеріледі. Жалпы балды немесе алдыңғы сынып мақсаттары бойынша балдарды енгізуге болады.'):(ru?'Учебные цели соответствуют классу участников.':'Оқу мақсаттары қатысушылар сыныбына сәйкес келеді.'));
 }
 document.addEventListener('change',event=>{if(event.target.matches('input[name="school_class_ids"]'))sync();});
 quarter.addEventListener('change',()=>mode.dispatchEvent(new Event('change',{bubbles:true})));
 type.addEventListener('change',()=>{sync();mode.dispatchEvent(new Event('change',{bubbles:true}));});
 sync();
})();
