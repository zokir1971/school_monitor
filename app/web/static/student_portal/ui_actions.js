/* School Monitor shared UI 167. Presentation and safe GET navigation only.
   No form values, submit handlers, answer state or fetch requests are changed. */
(() => {
 'use strict';
 const actions='button,a[href],input[type="submit"],input[type="reset"],input[type="button"]';
 const skip='[data-sm-no-style],math-field,.question-number,.work-plan-chip,.qb-bank-cell,.brand';
 const known=new Set(['nav','primary','success','edit','danger']);
 function classify(el){
  const text=(el.textContent||el.value||'').trim().toLowerCase(),cls=String(el.className||'').toLowerCase();
  if(/копир|көшіру|вставить|печать|снять.*(отмет|выдел)|таңдауды алып тастау|белгілерін алып тастау|показать область удаления|выйти/.test(text))return 'nav';
  if(/отменить подготов|отменить назнач|дайындаудан бас тарту|убрать из|алып тастау/.test(text))return 'danger';
  if(/отмена|отменить редакт|бас тарту|сбросить|очистить|тазарту|болдырмау/.test(text))return 'nav';
  if(/удал|delete|жою|\bremove\b/.test(text)||/danger|delete|remove-answer|remove-coexecutor/.test(cls)||/(^|\s)өшіру/.test(text))return 'danger';
  if(/без отч[её]та|есепсіз|освобод|босату|архив|мұрағат|отклон|қайтару|қабылдамау/.test(text))return 'edit';
  if(/заверш|аяқта|подпис|қол қою|на рассмотр|қарауға жібер|на исполнение|орындауға жібер|опубликовать результат|нәтижелерді жария|закрыть проведение|өткізуді жаб|сформировать pdf|pdf құру|pdf жасау|одобр|мақұлдау|утверд|бекіту/.test(text)||/btn[-_](success|complete|finish)/.test(cls))return 'success';
  if(/переназнач|қайта тағай|редакт|өңдеу|обновить|жаңарту|настро|баптау|изменить|өзгерту/.test(text))return 'edit';
  if(/сохран|сақтау|созда|құру|примен|қолдану|добав|қосу|загрузить|жүктеу|войти|кіру|назначить|тағайындау|толтыр|заполн/.test(text))return 'primary';
  if(el.tagName==='A'||el.type==='reset'||/назад|артқа|оралу|қайту|просмотр|қарау|показать|көрсету|скач|жүктеп алу|ашу|откры|перейти|к панели|панельге|←|→/.test(text))return 'nav';
  if(/primary/.test(cls))return 'primary';
  return el.type==='button'?'nav':'primary';
 }
 function normalize(el){
  if(el.closest(skip))return;
  const cls=String(el.className||'');
  if(el.tagName==='A'&&(/(?:^|\s)[\w-]*card(?:\s|$)/.test(cls)||el.querySelector('article,h1,h2,h3,h4,div')||/^(mailto:|tel:)/i.test(el.getAttribute('href')||'')))return;
  if(el.tagName==='A'&&el.target==='_blank'&&/^https?:/i.test(el.getAttribute('href')||'')&&!/btn|button|action/i.test(cls))return;
  if(!known.has(el.dataset.smAction)||el.dataset.smAuto==='1'){
   el.dataset.smAction=classify(el);el.dataset.smAuto='1';
   if(/btn[-_](sm|small|mini)|rich|tools|toolbar|close|ui-language__button|workspace-menu__item|header-btn/.test(cls))el.dataset.smSize='compact';
   if(/close/.test(cls)||/^[×✕✖]$/.test((el.textContent||'').trim()))el.dataset.smIcon='true';
  }
 }
 function scan(root){
  if(root.nodeType!==1&&root.nodeType!==9)return;
  if(root.matches?.(actions))normalize(root);
  root.querySelectorAll(actions).forEach(normalize);
 }
 function localURL(raw){
  if(!raw||/^\s*(#|javascript:|data:|mailto:|tel:)/i.test(raw))return null;
  try{const url=new URL(raw,location.href);return url.origin===location.origin&&/^https?:$/.test(url.protocol)?url:null;}catch(_){return null;}
 }
 function navigation(){
  if(document.body.hasAttribute('data-sm-student'))return;
  const nav=document.querySelector('[data-sm-global-navigation]');
  const current=new URL(location.href),user=document.body.dataset.smUser||'anonymous';
  if(user==='anonymous')return;
  const filterKeys=new Set(["academic_year","academic_year_start","category","category_id","checkpoint","class_id","class_ids","date_from","date_to","difficulty","direction_id","district_id","education_track","filter_district_id","filter_region_id","filter_school_id","grade","grade_level","input_mode","instruction_language","language","language_policy","limit","method_association_id","month","offset","origin","page","page_size","participant_grade","participant_id","plan_id","q","quarter","question_type","region_id","response_mode","review_place","reviewed","school_class_id","school_id","school_plan_id","scope","search","section","selected_task_id","settlement","sort","source_quarter","split","state","status","subject","subject_id","tab","task_review_id","teacher_choices","teacher_id","template_id","track","variant","work_type","year","year_start"]);
  const key='sm-navigation-v167:'+user+':'+(document.body.dataset.smWorkspace||'');let trail=[];
  try{const raw=JSON.parse(sessionStorage.getItem(key)||'[]');if(Array.isArray(raw))trail=raw.filter(x=>typeof x==='string'&&x.length<3000&&localURL(x)).slice(-40);}catch(_){}
  const candidates=[];
  const safe=url=>url&&url.pathname!==current.pathname&&!/\/(save|update|delete|complete|logout)\/?$/.test(url.pathname);
  if(nav){
   const back=nav.querySelector('[data-sm-nav-back]'),home=nav.querySelector('[data-sm-nav-home]');
   const explicit=[...document.querySelectorAll('a[data-sm-back]')].find(el=>!nav.contains(el)&&safe(localURL(el.getAttribute('href')))&&!el.closest('[hidden],.hidden,.is-hidden'));
   if(explicit){nav.hidden=true;}else{
    nav.hidden=false;
    // Prefer an actual visited ancestor (including its filters), never history.back().
    for(const raw of trail){const url=localURL(raw);if(safe(url)&&url.pathname!=='/'&&url.pathname!=='/dashboards'&&current.pathname.startsWith(url.pathname.replace(/\/$/,'')+'/'))candidates.push(url);}
    document.querySelectorAll('main a[href]').forEach(el=>{if(nav.contains(el))return;const url=localURL(el.getAttribute('href'));if(safe(url)&&url.pathname!=='/'&&url.pathname!=='/dashboards'&&current.pathname.startsWith(url.pathname.replace(/\/$/,'')+'/'))candidates.push(url);});
    candidates.sort((a,b)=>b.pathname.length-a.pathname.length);
    let parent=candidates[0];
    if(!parent){const path=current.pathname;let fallback=null;
     if(path.startsWith('/staff/school/members/'))fallback='/staff/school';
     else if(path.startsWith('/staff/tasks/'))fallback='/staff/tasks';
     else if(path.startsWith('/planning/school/'))fallback='/planning/school';
     else if(path.startsWith('/planning/super/')&&!path.startsWith('/planning/super/education/'))fallback='/planning/super/directions';
     if(fallback&&fallback!==path){parent=localURL(fallback);if(fallback==='/staff/tasks'&&current.searchParams.has('month'))parent.searchParams.set('month',current.searchParams.get('month'));}
    }
    if(parent){
     // When a DOM ancestor was found, reuse its last visited filter state if present.
     const prior=[...trail].reverse().map(localURL).find(url=>url&&url.pathname===parent.pathname);
     if(prior)parent=prior;
     back.href=parent.pathname+parent.search+parent.hash;
     back.textContent=document.documentElement.lang==='ru'?'← Назад':'← Артқа';
     home.hidden=parent.pathname==='/dashboards';
    }else{back.href='/dashboards';back.textContent=document.documentElement.lang==='ru'?'← Назад к панели':'← Панельге оралу';home.hidden=true;}
   }
  }
  // Store only GET locations, without entry codes, tokens, passwords or fragments.
  if((!document.body.dataset.smMethod||document.body.dataset.smMethod==='GET')&&!/\/(save|update|delete|complete|logout)\/?$/.test(current.pathname)&&![...current.searchParams.keys()].some(k=>/token|password|secret|code/i.test(k))){
   const clean=new URL(current.href);for(const key of [...clean.searchParams.keys()])if(!filterKeys.has(key))clean.searchParams.delete(key);const here=clean.pathname+clean.search;if(here.length>=3000)return;
   if(trail[trail.length-1]!==here){trail.push(here);try{sessionStorage.setItem(key,JSON.stringify(trail.slice(-40)));}catch(_){}}
  }
 }
 function start(){
  scan(document);navigation();
  // Native buttons keep their disabled behavior. Guard existing aria-disabled links too.
  document.addEventListener('click',event=>{const el=event.target.closest?.('a[data-sm-action][aria-disabled="true"]');if(el){event.preventDefault();event.stopImmediatePropagation();}},true);
  const pending=new Set();let frame=0;
  const flush=()=>{frame=0;const nodes=[...pending];pending.clear();const roots=new Set(nodes);for(const node of nodes){if(!node.isConnected)continue;let covered=false;for(let p=node.parentElement;p;p=p.parentElement)if(roots.has(p)){covered=true;break;}if(!covered)scan(node);}};
  const observer=new MutationObserver(records=>{for(const record of records){if(record.type==='attributes'){if(record.target.matches(actions)&&record.target.dataset.smAuto==='1')normalize(record.target);}else for(const node of record.addedNodes)if(node.nodeType===1)pending.add(node);}if(pending.size&&!frame)frame=requestAnimationFrame(flush);});
  observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class']});
  document.body.addEventListener('htmx:afterSwap',navigation);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
})();
