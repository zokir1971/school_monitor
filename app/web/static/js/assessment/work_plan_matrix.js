(() => {
 'use strict';
 const dialog=document.querySelector('[data-position-dialog]');if(!dialog)return;
 const body=dialog.querySelector('[data-position-dialog-body]');
 document.addEventListener('click',event=>{
  const button=event.target.closest('[data-position-preview]');if(!button)return;
  const template=document.getElementById(button.dataset.positionPreview);if(!template)return;
  body.replaceChildren(template.content.cloneNode(true));
  if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','');
  dialog.scrollTop=0;
 });
 const close=()=>{if(typeof dialog.close==='function')dialog.close();else dialog.removeAttribute('open');body.replaceChildren();};
 dialog.querySelector('[data-position-close]').addEventListener('click',close);
 dialog.addEventListener('close',()=>body.replaceChildren());
 dialog.addEventListener('click',event=>{
  const rect=dialog.getBoundingClientRect();
  if(event.target===dialog&&(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom))close();
 });
})();
