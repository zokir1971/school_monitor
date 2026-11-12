(() => {
'use strict';
const normalizeNumber = value => String(value ?? '').trim().replace(/^№\s*/, '');
function buildProgram(subject, first, last, language, track='') {
 if(!subject?.id || !subject.kz || !['kz','ru'].includes(language)) return null;
 const from=Number(first), to=Number(last);
 if(!Number.isInteger(from)||!Number.isInteger(to)||from<1||to>12||from>to) return null;
 const upper=from<=11 && to>=10;
 if(upper && (from<10||to>11||!['emn','ogn'].includes(track))) return null;
 if(!upper && track) return null;
 const code=String(subject.code||'').trim().toLowerCase().replace(/[^a-z0-9_-]+/g,'-').replace(/^-+|-+$/g,'');
 if(!code) return null;
 const range=from===to?String(from):`${from}–${to}`;
 const kzTrack=track==='emn'?', жаратылыстану-математикалық бағыт':track==='ogn'?', қоғамдық-гуманитарлық бағыт':'';
 const ruTrack=track==='emn'?', естественно-математическое направление':track==='ogn'?', общественно-гуманитарное направление':'';
 return {
  program_title_kz:`${subject.kz}, ${from===to?range+'-сынып':range+' сыныптар'}${kzTrack}, ${language==='kz'?'қазақ':'орыс'} тілінде оқыту`,
  program_title_ru:`${subject.ru||subject.kz}, ${range} ${from===to?'класс':'классы'}${ruTrack}, обучение на ${language==='kz'?'казахском':'русском'} языке`,
  variant_key:`${code}-grade-${from===to?from:from+'-'+to}${track?'-'+track:''}-${language}`
 };
}
function buildDocumentKey(number,date,edition) {
 const clean=normalizeNumber(number);
 if(!clean || !/^\d{4}-\d{2}-\d{2}$/.test(date)|| !/^\d{4}-\d{2}-\d{2}$/.test(edition)) return '';
 const slug=clean.normalize('NFKD').replace(/[^a-zA-Z0-9\u0400-\u04ff]+/g,'-').replace(/^-|-$/g,'').toLowerCase();
 return slug?`order-${slug}-${date}-edition-${edition}`:'';
}
window.LearningObjectiveImportAutofill={buildProgram,buildDocumentKey};
for(const form of document.querySelectorAll('[data-objective-autofill]')) {
 const get=name=>form.elements.namedItem(name);
 const generated=['program_title_kz','program_title_ru','variant_key','document_key'];
 const manual=new Set(generated.filter(name=>get(name)?.value.trim()));
 for(const name of generated) get(name)?.addEventListener('input',()=>{
  if(get(name).value.trim())manual.add(name);else manual.delete(name);
 });
 const edition=get('edition_date'), mode=get('edition_mode'), track=get('education_track');
 function set(name,value){const field=get(name);if(field&&!manual.has(name))field.value=value||'';}
 function refresh(){
  const subject=get('subject_id'), option=subject?.selectedOptions[0];
  const first=get('grade_level')?.value||get('grade_from')?.value;
  const last=get('grade_level')?.value||get('grade_to')?.value;
  const upper=Number(first)<=11 && Number(last)>=10;
  if(track){
   track.disabled=!upper;track.required=upper;
   form.querySelector('[data-track-wrap]').hidden=!upper;
   if(!upper)track.value='';
  }
  const program=buildProgram(option?.value?{id:option.value,code:option.dataset.code,kz:option.dataset.nameKz,ru:option.dataset.nameRu}:null,first,last,get('instruction_language')?.value,track?.value||'');
  for(const name of ['program_title_kz','program_title_ru','variant_key'])set(name,program?.[name]);
  if(mode&&edition){edition.readOnly=mode.value==='original';if(edition.readOnly)edition.value=get('order_date')?.value||'';}
  set('document_key',buildDocumentKey(get('order_number')?.value,get('order_date')?.value,edition?.value));
 }
 for(const name of ['subject_id','grade_level','grade_from','grade_to','education_track','instruction_language','order_number','order_date','edition_date','edition_mode']) {
  get(name)?.addEventListener('change',refresh);
  if(name==='order_number')get(name)?.addEventListener('input',refresh);
 }
 mode?.addEventListener('change',()=>{if(mode.value==='revised')edition.value='';refresh();});
 form.querySelector('[data-refresh-generated]')?.addEventListener('click',()=>{manual.clear();refresh();});
 refresh();
}
})();
