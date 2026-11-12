(() => {
 function init(){
  const form=document.getElementById('qb-ai-generate');if(!form)return;
  const block=form.querySelector('[data-ai-image-options]');if(!block)return;
  const files=[...block.querySelectorAll('[data-ai-option-file]')];
  function refresh(){
   const types=[...form.querySelectorAll('[data-plan-type]')];
   const active=types.some(input=>input.value==='image_choice');block.hidden=!active;
   files.forEach(input=>{input.disabled=!active;input.required=active;});
   types.forEach(input=>{
    const count=input.closest('[data-plan-rows]') ? input.parentElement.parentElement.querySelector('[data-plan-count]') : null;
    if(count)count.setCustomValidity(active&&(types.length!==1||Number(count.value)!==1)?block.dataset.constraint:'');
   });
  }
  const source=form.querySelector('[name=source_image]');
  const previewFiles=source?[...files,source]:files;
  previewFiles.forEach(input=>input.addEventListener('change',()=>{
   const preview=input.parentElement.querySelector('img');if(preview.dataset.url)URL.revokeObjectURL(preview.dataset.url);
   preview.hidden=true;input.setCustomValidity('');
   const file=input.files[0];if(!file)return;
   if(file.size>5*1024*1024){input.setCustomValidity('Maximum 5 MB / Ең көбі 5 МБ');input.reportValidity();return;}
   const url=URL.createObjectURL(file);preview.dataset.url=url;preview.src=url;preview.hidden=false;
  }));
  form.addEventListener('change',refresh);
  form.addEventListener('input',refresh);
  form.addEventListener('submit',event=>{refresh();if(!form.checkValidity()){event.preventDefault();event.stopImmediatePropagation();form.reportValidity();}},true);
  new MutationObserver(refresh).observe(form.querySelector('[data-plan-rows]'),{childList:true});
  refresh();
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
