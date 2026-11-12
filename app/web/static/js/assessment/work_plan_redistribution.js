(() => {
 'use strict';
 const form=document.querySelector('[data-redistribution-form]');if(!form)return;
 const boxes=[...form.querySelectorAll('input[name="group_keys"]')],totals=[...form.querySelectorAll('[data-redistributed-total]')];
 // Work-plan scores have two decimal places; calculate in integer hundredths.
 const cents=text=>{const parts=String(text).split('.');return Number(parts[0])*100+Number((parts[1]||'').padEnd(2,'0').slice(0,2));};
 const show=n=>(n/100).toFixed(2);
 const update=()=>{const reduction=boxes.filter(b=>b.checked).reduce((n,b)=>n+cents(b.dataset.reduction),0);for(const total of totals)total.textContent=show(cents(total.dataset.before)-reduction);};
 for(const box of boxes)box.addEventListener('change',update);
 form.addEventListener('submit',event=>{if(!boxes.some(b=>b.checked)){event.preventDefault();const error=form.querySelector('[data-redistribution-error]');error.hidden=false;error.textContent=form.dataset.empty;}});
 update();
})();
