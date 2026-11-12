/* Count policy only: existing fill-gap source, preview, alternatives and bank stay intact. */
(() => {
  function init(){
    const group=document.getElementById('fill-gaps-fields');if(!group||group.dataset.fillScoreReady)return;
    const form=group.closest('form'),type=form.querySelector('[name="question_type"]'),score=(window.QBAuthoringScore?.countInput(form) || form.querySelector('[name="max_score"]')),source=group.querySelector('[name="fill_gaps_text"]'),status=group.querySelector('[data-fill-score-status]');
    let initial={};
    try{const el=document.getElementById('qb-initial-item');if(el)initial=JSON.parse(el.dataset.initialItem);}
    catch(error){status.textContent=window.SchoolMonitorI18n.t("qb_eb5a04324d8e");form.addEventListener('submit',e=>{if(type.value==='fill_gaps')e.preventDefault();});return;}
    const legacy=initial.question_type==='fill_gaps'&&initial.grading_settings?.fill_gaps_score_policy!=='per_gap_v1';
    group.dataset.fillScoreReady='1';
    function countSource(){
      const text=source.value,pattern=/\[\[([^\[\]\r\n]+)]]/g,matches=[...text.matchAll(pattern)],rest=text.replace(pattern,'');
      if(rest.includes('[[')||rest.includes(']]')||matches.some(match=>!match[1].trim()||(match.index>0&&text[match.index-1]==='[')||(match.index+match[0].length<text.length&&text[match.index+match[0].length]===']')))return {count:matches.length,error:window.SchoolMonitorI18n.t("qb_d312baab66c6")};
      return {count:matches.length,error:''};
    }
    function refresh(){
      if(type.value!=='fill_gaps'){source.setCustomValidity('');return true;}
      if(legacy){status.textContent=window.SchoolMonitorI18n.t("qb_cb01ded4479f");return true;}
      const n=Number(score.value),validScore=Number.isInteger(n)&&n>=1&&n<=100;
      score.setCustomValidity(validScore?'':window.SchoolMonitorI18n.t("qb_20df6372b571"));
      const parsed=countSource();let message=parsed.error;
      if(!message&&validScore&&parsed.count!==n)message=window.SchoolMonitorI18n.t("qb_2a3e7aefe8ee", {p0: (n), p1: (parsed.count)});
      if(!message&&!parsed.count)message=window.SchoolMonitorI18n.t("qb_6ddea1d3a381");
      source.setCustomValidity(message);
      status.textContent=!validScore?window.SchoolMonitorI18n.t("qb_6e48cc6c5d41"):message||window.SchoolMonitorI18n.t("qb_2bb355093cbc", {p0: (parsed.count), p1: (n)});
      status.style.color=(!validScore||message)?'#b42318':'#027a48';
      return validScore&&!message;
    }
    source.addEventListener('input',refresh);source.addEventListener('change',refresh);score.addEventListener('input',refresh);score.addEventListener('change',refresh);type.addEventListener('change',refresh);
    form.addEventListener('submit',event=>{if(type.value==='fill_gaps'&&!refresh()){event.preventDefault();if(!score.validity.valid)score.reportValidity();else source.reportValidity();}},true);
    refresh();
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(init,0));else setTimeout(init,0);
})();
