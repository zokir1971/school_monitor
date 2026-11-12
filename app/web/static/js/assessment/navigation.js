/* Tab-local list context and short-lived scroll restoration; no answer/form data. */
(() => {
 'use strict';
 const root=document.querySelector('[data-assessment-ui]');if(!root)return;
 const prefix='sm:assessment-ui:v99:'+root.dataset.user+':',now=()=>Date.now();
 const read=k=>{try{return JSON.parse(sessionStorage.getItem(prefix+k)||'null');}catch{return null;}};
 const write=(k,v)=>{try{sessionStorage.setItem(prefix+k,JSON.stringify(v));}catch{}};
 const allowed=path=>path==='/assessment/question-bank/catalog'||path==='/teacher/question-bank/catalog'||path.startsWith('/assessment/work-plans')||path.startsWith('/assessment/diagnostics');
 const url=value=>{try{const u=new URL(value,location.href);return u.origin===location.origin&&allowed(u.pathname)?u:null;}catch{return null;}};
 const here=()=>url(location.href);
 function snapshot(){
  const current=here();if(!current)return;
  write('position:'+current.pathname,{y:window.scrollY,time:now()});
  if(current.pathname==='/assessment/work-plans')write('list',current.pathname+current.search);
 }
 function remember(form){
  if(form?.matches('form.ui-language'))return;
  const current=here();if(!current)return;
  snapshot();
  const target=(form?.method||'get').toLowerCase()==='get'?url(form?.action||location.href):current;
  if(target&&target.pathname===current.pathname)write('pending',{path:target.pathname,y:window.scrollY,time:now()});
 }
 window.SchoolAssessmentUI={remember};
 const current=here();
 if(current?.pathname==='/assessment/work-plans')write('list',current.pathname+current.search);
 const savedList=url(read('list'));
 if(savedList?.pathname==='/assessment/work-plans')for(const link of document.querySelectorAll('[data-assessment-list]'))link.href=savedList.pathname+savedList.search;
 document.addEventListener('submit',e=>{if(root.contains(e.target))remember(e.target);},true);
 document.addEventListener('click',e=>{
  const link=e.target.closest('a[href]');if(!link||!root.contains(link)||link.target==='_blank'||link.hasAttribute('download'))return;
  snapshot();const target=url(link.href);if(!target||target.hash||link.hasAttribute('data-assessment-reset'))return;
  const position=read('position:'+target.pathname);
  if(position&&now()-position.time<1800000)write('pending',{path:target.pathname,y:position.y,time:now()});
 },true);
 window.addEventListener('pagehide',snapshot);
 const pending=read('pending');
 try{sessionStorage.removeItem(prefix+'pending');}catch{}
 if(!pending||pending.path!==current?.pathname||!Number.isFinite(pending.time)||!Number.isFinite(pending.y)||pending.y<0||now()-pending.time>120000||now()<pending.time||location.hash)return;
 function restore(){
  let stopped=false,observer;
  const events=['wheel','touchstart','pointerdown','keydown'];
  const apply=()=>{if(!stopped)window.scrollTo({top:pending.y,left:0,behavior:'instant'});};
  const stop=()=>{stopped=true;observer?.disconnect();for(const n of events)window.removeEventListener(n,stop,true);};
  for(const n of events)window.addEventListener(n,stop,{capture:true,passive:true});
  apply();window.addEventListener('load',apply,{once:true});
  if(typeof ResizeObserver!=='undefined'){observer=new ResizeObserver(apply);observer.observe(document.body);}
  window.setTimeout(stop,2000);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',restore,{once:true});else restore();
})();
