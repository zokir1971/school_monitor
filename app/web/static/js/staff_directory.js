/* Only the selected employee form is submitted. Server rechecks school, CSRF and revision. */
(()=>{
 'use strict';
 const root=document.querySelector('.staff-directory');if(!root)return;
 const initial=new WeakMap();
 function renumber(form){form.querySelectorAll('[data-staff-role-rows] .staff-role-row').forEach((row,i)=>{
  row.querySelector('[data-staff-role-select]').name=`roles[${i}].role`;
  row.querySelector('[data-staff-role-context]').name=`roles[${i}].context`;
 });}
 function close(form){
  const editor=form.closest('.staff-role-editor');editor.hidden=true;
  const toggle=root.querySelector(`[aria-controls="${editor.id}"]`);toggle?.setAttribute('aria-expanded','false');toggle?.focus();
 }
 root.addEventListener('click',event=>{
  const toggle=event.target.closest('[data-staff-role-toggle]');
  if(toggle){event.preventDefault();const editor=document.getElementById(toggle.getAttribute('aria-controls')),form=editor.querySelector('form');
   if(!initial.has(form))initial.set(form,form.querySelector('[data-staff-role-rows]').innerHTML);
   editor.hidden=!editor.hidden;toggle.setAttribute('aria-expanded',String(!editor.hidden));
   if(!editor.hidden&&!form.querySelector('[data-staff-role-select]')){form.querySelector('[data-staff-role-rows]').append(form.querySelector('template').content.cloneNode(true));renumber(form);}
   if(!editor.hidden)(form.querySelector('[data-staff-role-select]')||form.querySelector('[data-staff-role-add]')).focus();return;
  }
  const button=event.target.closest('button');if(!button)return;const form=button.closest('[data-staff-role-form]');if(!form)return;
  if(button.hasAttribute('data-staff-role-add')){const rows=form.querySelector('[data-staff-role-rows]');if(rows.children.length>=50)return;
   rows.append(form.querySelector('template').content.cloneNode(true));renumber(form);rows.lastElementChild.querySelector('select').focus();
  }else if(button.hasAttribute('data-staff-role-remove')){button.closest('.staff-role-row').remove();renumber(form);(form.querySelector('[data-staff-role-select]')||form.querySelector('[data-staff-role-add]')).focus();
  }else if(button.hasAttribute('data-staff-role-cancel')){form.querySelector('[data-staff-role-rows]').innerHTML=initial.get(form)||'';form.reset();close(form);}
 });
 const filterKeys=['name','iin','role','status','page'];
 function storageKey(values=new URL(location.href).searchParams){const query=new URLSearchParams();
  for(const k of filterKeys){const value=values.get(k)||(k==='page'?'1':k==='status'?'active':'');if(value)query.set(k,value);}
  return 'staff-directory-scroll342:'+document.body.dataset.smUser+':'+root.dataset.schoolId+':'+query.toString();}
 root.addEventListener('submit',event=>{
  const form=event.target.closest('[data-staff-role-form]');if(!form)return;renumber(form);
  const selected=[...form.querySelectorAll('[data-staff-role-select]')].some(el=>el.value);
  if(!selected&&form.dataset.hadRoles==='1'&&!confirm(form.dataset.emptyConfirm)){event.preventDefault();return;}
  try{sessionStorage.setItem(storageKey(new FormData(form)),JSON.stringify({y:scrollY,time:Date.now()}));}catch(_){}
 });
 if(new URL(location.href).searchParams.has('roles_saved')){
  try{const key=storageKey(),value=JSON.parse(sessionStorage.getItem(key)||'null');sessionStorage.removeItem(key);
   if(value&&Number.isFinite(value.y)&&Date.now()-value.time<120000)requestAnimationFrame(()=>scrollTo({top:value.y,behavior:'instant'}));
  }catch(_){}
 }
})();
