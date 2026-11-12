/* Restore position and unsaved non-sensitive controls across planning actions. */
(() => {
  'use strict';
  const script = document.currentScript;
  if (!/^\/(planning\/school|staff\/(tasks|reports|reviews))(\/|$)/.test(location.pathname)) return;
  const user = script.dataset.user || 'anonymous';
  const url = new URL(location.href);
  const identity = new URLSearchParams();
  ['month','month_plan_id','school_plan_id','selected_task_id','review_place','method_association_id','year','school_id','task_review_id'].forEach(k => {
    if (url.searchParams.has(k)) identity.set(k,url.searchParams.get(k));
  });
  const key = 'sm-planning-v1:' + user + ':' + location.pathname + '?' + identity;
  const positionKey = 'sm-planning-position-v1:' + user + ':' + location.pathname;
  const now = Date.now(), ttl = 30 * 60 * 1000;
  const failed = url.searchParams.has('error') || url.searchParams.has('warning');
  const success = url.searchParams.has('success');
  let previous = null, restoring = true, touched = false;
  try { previous = JSON.parse(sessionStorage.getItem(key)); } catch (_) {}
  if (!previous || now - previous.at > ttl) previous = null;
  if (!previous) {
    try {
      const position = JSON.parse(sessionStorage.getItem(positionKey));
      if (position && now - position.at <= ttl) previous = {...position, fields:[], dirty:false};
    } catch (_) {}
  }
  const controls = () => [...document.querySelectorAll('input[name],select[name],textarea[name]')].filter(e => (!e.form || (e.form.getAttribute('method') || 'get').toLowerCase() !== 'get') && !e.closest('[data-no-draft-restore]') && !['hidden','password','file','submit','button'].includes(e.type) && !/token|password|secret/i.test(e.name));
  function capture() {
    if (restoring) return;
    const counters = {};
    const fields = controls().map(e => {
      const k = e.form?.id || e.form?.getAttribute('action') || 'page';
      const id = k + ':' + e.name, index = counters[id] || 0;
      counters[id] = index + 1;
      return {id, index, values:e.tagName === 'SELECT' ? [...e.selectedOptions].map(o=>o.value) : null, value:e.value, checked:e.checked};
    });
    try {
      const position = {at:Date.now(), x:scrollX, y:scrollY};
      sessionStorage.setItem(key, JSON.stringify({...position, fields, dirty:touched}));
      sessionStorage.setItem(positionKey, JSON.stringify(position));
    } catch (_) {}
  }
  function restore() {
    if (previous && previous.dirty && !url.searchParams.has('reset_form') && (failed || !success || url.searchParams.has('restore_plan_draft'))) {
      const counters = {}, values = new Map(previous.fields.map(f=>[f.id+':'+f.index,f]));
      controls().forEach(e => {
        const k = e.form?.id || e.form?.getAttribute('action') || 'page';
        const id = k+':'+e.name, index = counters[id] || 0; counters[id] = index+1;
        const savedInclusion = url.searchParams.get('saved_inclusion_item');
        if (success && /^\d+$/.test(savedInclusion || '') && e.name === 'item_' + savedInclusion + '_included') return;
        const savedSchedule = url.searchParams.get('saved_schedule_item');
        if (success && /^\d+$/.test(savedSchedule || '') && e.name === 'item_' + savedSchedule + '_week') return;
        const saved = values.get(id+':'+index);
        const assignmentCo = e.form?.id === 'assignee-form' && e.name === 'co_executor_staff_role_ids';
        if (!saved || (e.disabled && !assignmentCo)) return;
        if (e.tagName === 'SELECT') [...e.options].forEach(o=>{o.selected = saved.values.includes(o.value);});
        else if (e.type === 'checkbox' || e.type === 'radio') e.checked = saved.checked;
        else e.value = saved.value;
      });
      const assignmentPrimary = controls().find(e => e.form?.id === 'assignee-form' && e.name === 'primary_staff_role_id' && e.checked);
      if (assignmentPrimary && typeof Event !== 'undefined') assignmentPrimary.dispatchEvent(new Event('change', {bubbles:true}));
      touched = true;
    }
    let interrupted = false;
    ['wheel','touchstart','pointerdown','keydown'].forEach(event => addEventListener(event,()=>{interrupted=true;}, {once:true,passive:true}));
    const position = () => { if (previous && !interrupted && !document.querySelector('[data-plan-outcome]')) scrollTo(previous.x,previous.y); };
    requestAnimationFrame(position);
    addEventListener('load', position, {once:true});
    // Late images and asynchronous layout must not undo the restored position.
    const observer = new ResizeObserver(position); observer.observe(document.body);
    setTimeout(()=>observer.disconnect(), 1500);
    restoring = false;
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',restore,{once:true}); else restore();
  document.addEventListener('input',()=>{touched=true;capture();});
  document.addEventListener('change',()=>{touched=true;capture();});
  document.addEventListener('submit',capture,true);
  document.addEventListener('click',e=>{if(e.target.closest('a')) capture();},true);
  addEventListener('pagehide',capture);
})();
