/* Printing uses browser PDF output, after fonts/formulas/images are ready. */
(() => {
  const button=document.querySelector('[data-print-work]');
  const status=document.querySelector('[data-print-status]');
  if(!button || !status)return;
  const bounded=(promise,ms=20000)=>new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('timeout')),ms);
    promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});
  });
  button.addEventListener('click',async()=>{
    button.disabled=true;status.textContent=status.dataset.wait;
    try{
      const fields=[...document.querySelectorAll('math-field')];
      if(fields.length){
        await bounded(customElements.whenDefined('math-field'));
        // Read-only MathLive fields render their shadow DOM in the browser print engine.
        // Wait for component rendering and font requests; keep the original formula intact.
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      }
      await bounded(document.fonts.ready);
      const images=[...document.querySelectorAll('.work-document img')];
      await bounded(Promise.all(images.map(async image=>{
        image.loading='eager';
        if(image.decode)await image.decode();
        else if(!image.complete)await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;});
        if(!image.naturalWidth)throw new Error('image failed');
      })));
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      // Short choices use two columns. Give a long formula a full-width row.
      const options=[...document.querySelectorAll('.document-task--single_choice .qb-render-option, .document-task--multiple_choice .qb-render-option')];
      options.forEach(option=>option.classList.remove('document-option-wide'));
      const wide=options.filter(option=>{
        const body=option.querySelector('.qb-render-option__body');
        if(!body || !body.clientWidth)return false;
        return body.scrollWidth>body.clientWidth+1 || [...body.querySelectorAll('math-field')].some(field=>
          Math.max(field.scrollWidth,field.getBoundingClientRect().width)>body.clientWidth*.94);
      });
      wide.forEach(option=>option.classList.add('document-option-wide'));
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      status.textContent='';window.print();
    }catch(error){status.textContent=status.dataset.failed;}
    finally{button.disabled=false;}
  });
})();
