(() => {
 const init=()=>{
  const popup=document.getElementById('qb-bank-hover'),dialog=document.getElementById('qb-bank-dialog');
  if(!popup||!dialog)return;
  const body=dialog.querySelector('[data-bank-dialog-body]');let timer,active,returnFocus;
  const clone=(id,target)=>{
   const template=document.getElementById(id);if(!template?.content)return false;
   target.replaceChildren(template.content.cloneNode(true));
   if(window.QBMathProse)target.querySelectorAll('[data-readable-math-prose]').forEach(node=>{node.textContent=window.QBMathProse.convert(node.textContent);});
   return true;
  };
  function hide(){clearTimeout(timer);popup.hidden=true;active?.removeAttribute('aria-describedby');active=null;popup.replaceChildren();}
  function soon(){clearTimeout(timer);timer=setTimeout(hide,220);}
  function show(button){
   if(dialog.open)return;
   clearTimeout(timer);if(active!==button){hide();if(!clone(button.dataset.bankPreview,popup))return;active=button;}
   popup.hidden=false;button.setAttribute('aria-describedby',popup.id);
   const rect=button.getBoundingClientRect(),width=popup.offsetWidth,height=popup.offsetHeight;
   popup.style.left=Math.max(12,Math.min(rect.left,window.innerWidth-width-12))+'px';
   popup.style.top=Math.max(12,Math.min(rect.bottom+8,window.innerHeight-height-12))+'px';
  }
  const hover=window.matchMedia('(hover: hover)').matches;
  document.querySelectorAll('[data-bank-preview]').forEach(button=>{
   if(hover){button.addEventListener('mouseenter',()=>show(button));button.addEventListener('mouseleave',soon);}
   button.addEventListener('click',()=>{hide();if(!clone(button.dataset.bankPreview,body))return;returnFocus=button;dialog.showModal();});
  });
  popup.addEventListener('mouseenter',()=>clearTimeout(timer));popup.addEventListener('mouseleave',soon);
  dialog.querySelector('[data-bank-close]').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{body.replaceChildren();returnFocus?.focus();});
  document.addEventListener('keydown',event=>{if(event.key==='Escape')hide();});
  window.addEventListener('resize',hide);window.addEventListener('scroll',event=>{if(!popup.contains(event.target))hide();},true);
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
