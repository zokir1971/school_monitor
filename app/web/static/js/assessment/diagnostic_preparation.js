(() => {
 'use strict';
 const panel=document.querySelector('[data-preparation-state]');if(!panel)return;
 try {
  const key='sm:diagnostic-create:v97:'+panel.dataset.draftKey;
  const draft=JSON.parse(sessionStorage.getItem(key)||'null');
  if(draft?.fields?.request_key===panel.dataset.requestKey)sessionStorage.removeItem(key);
 } catch(e) { /* Tab storage is optional. */ }
 if(['queued','running'].includes(panel.dataset.preparationState)){
  window.setTimeout(()=>{if(!document.hidden)window.location.reload();},5000);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)window.location.reload();});
 }
})();
