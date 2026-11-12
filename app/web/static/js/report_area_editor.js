/* Report areas are explicit, school/year-scoped pairs. The server compiles all targets. */
(() => {
  'use strict';
  const supported = ['knowledge_quality_table', 'class_summary'];
  const read = (text, fallback) => { try { return JSON.parse(text); } catch (_) { return fallback; } };
  const token = p => `${p.subject_id}:${p.class_id}`;
  const el = (tag, text, cls) => { const n=document.createElement(tag); if(text)n.textContent=text; if(cls)n.className=cls; return n; };
  const button = (text, action, danger=false) => {
    const b=el('button',text,'btn '+(danger?'btn--danger':'btn--secondary'));
    b.type='button'; b.style.cssText='white-space:nowrap;word-break:normal;flex-shrink:0';
    b.addEventListener('click', action); return b;
  };
  const checkbox = (text, checked, action) => {
    const label=el('label');label.style.cssText='display:inline-flex;gap:7px;align-items:center;margin:5px 12px 5px 0';
    const input=el('input');input.type='checkbox';input.checked=checked;input.style.width='auto';
    input.addEventListener('change',()=>action(input.checked));label.append(input,el('span',text));return label;
  };
  function init(root) {
    if(root._reportAreaEditor)return root._reportAreaEditor;
    const state=read(root.querySelector('#task-execution-json-data')?.dataset.state,{});
    const user=document.body?.dataset.smUser || document.body?.dataset.user || '';
    const task=root.querySelector('[name="selected_task_id"]')?.value;
    // A changed server revision invalidates an old local draft, including after successful saves.
    const key=user && task ? `sm-report-areas:186:${user}:${task}` : null;
    let data={enabled:!!state.report_areas_mode,areas:state.report_areas || [],coverage_exclusions:state.report_area_exclusions||[]};
    if(key)try {
      const draft=read(sessionStorage.getItem(key),null);
      if(draft && draft.revision===(state.algorithm_revision||0) && Date.now()-draft.at<1800000 && typeof draft.data?.enabled==='boolean' && Array.isArray(draft.data.areas))data=draft.data;
    }catch(_){}
    const host=el('section');host.dataset.reportAreaEditor='';host.style.cssText='margin-top:20px;padding:18px;border:1px solid #dbe3ef;border-radius:12px;background:#fff';
    const matrix=root.querySelector('[data-algorithm-matrix]');
    (matrix.closest('#report-teacher-targets') || matrix).after(host);
    const hidden=el('input');hidden.type='hidden';hidden.name='report_areas_json';root.append(hidden);
    const editor={data,host,hidden,key,revision:state.algorithm_revision||0,open:new Set(),profile:''};root._reportAreaEditor=editor;
    hidden.value=JSON.stringify(data);return editor;
  }
  function update(root, editor, changed=true) {
    editor.syncOverview?.();
    editor.hidden.value=JSON.stringify(editor.data);
    if(changed && editor.key)try {sessionStorage.setItem(editor.key,JSON.stringify({revision:editor.revision,at:Date.now(),data:editor.data}));}catch(_){}
    window.updateGeneratedMaterialsPreview?.(root,editor.flow);
  }
  function refresh(root, flow, view, input) {
    if(!root.querySelector('[data-algorithm-matrix]'))return;
    const e=init(root);e.flow=flow;
    const ru=root.querySelector('[data-algorithm-matrix]').dataset.language==='ru';
    const t=(a,b)=>ru?a:b;
    const selected=new Set(Array.from(root.querySelectorAll('input[name="report_types"]')).filter(n=>n.checked).map(n=>n.value));
    const codes=supported.filter(c=>selected.has(c));
    const catalog=flow.algorithm_catalog, classes=new Map(catalog.classes.map(c=>[c.id,c]));
    const selectedClasses=new Set(view.selected.map(c=>c.id)), subjects=new Set(input.subjects.map(Number));
    const pairs=(catalog.subject_classes||catalog.teaching).filter(p=>selectedClasses.has(p.class_id)&&(!subjects.size||subjects.has(p.subject_id)));
    const unique=new Map(pairs.map(p=>[token(p),{subject_id:p.subject_id,class_id:p.class_id}]));
    const allowed=new Set(unique.keys());
    const labels={knowledge_quality_table:t('Таблица качества знаний','Білім сапасының кестесі'),class_summary:t('Таблица обобщённого анализа','Жалпылама талдау кестесі')};
    const draw=()=>refresh(root,flow,view,input);
    e.host.hidden=!codes.length&&!e.data.enabled&&!e.data.areas.length;
    e.host.replaceChildren(el('h3',t('Области отчётов','Есеп ауқымдары') + ' · ' + e.data.areas.length));
    e.host.append(checkbox(t('Объединять предметы и классы в отдельные отчёты','Пәндер мен сыныптарды жеке есептерге біріктіру'),e.data.enabled,value=>{e.data.enabled=value;update(root,e);draw();}));
    e.host.append(el('p',t('Для качества знаний и обобщённого анализа. Каждая область распределяется отдельно. При включении создаются отчёты только для указанных областей; остальные типы сохраняют свой порядок.','Білім сапасы мен жалпылама талдау үшін. Әр ауқым бөлек бөлінеді. Қосылғанда осы ауқымдар үшін ғана есептер жасалады; басқа есеп түрлерінің тәртібі сақталады.')));
    window.ReportAreaPlanner?.render({root,e,flow,catalog,codes,unique,classes,ru,draw,update,el,button,checkbox});
    if(!e.data.enabled){update(root,e,false);return;}
    const advanced=el('details');advanced.append(el('summary',t('Дополнительно: добавить область вручную','Қосымша: ауқымды қолмен қосу')));e.host.append(advanced);
    const tools=el('div');tools.style.cssText='display:flex;gap:8px;flex-wrap:wrap;align-items:center';
    const profile=el('select');profile.style.cssText='max-width:320px;min-height:38px';profile.setAttribute('aria-label',t('Методический профиль','Әдістемелік бейін'));
    const any=el('option',t('Все предметы параметров','Параметрлердегі барлық пәндер'));any.value='';profile.append(any);
    (catalog.method_profiles||[]).forEach(p=>{const o=el('option',p.name||p.code);o.value=String(p.id);profile.append(o);});Array.from(profile.options).forEach(o=>{o.selected=o.value===e.profile;});
    profile.addEventListener('change',()=>{e.profile=profile.value;});tools.append(profile);
    const add=(lo,hi)=>{
      if(e.data.areas.length>=50){e.notice='limit';draw();return;}
      const mp=(catalog.method_profiles||[]).find(p=>String(p.id)===e.profile);
      const profilePairs=mp?new Set(mp.pairs.map(token)):null;
      const chosen=lo?Array.from(unique.values()).filter(p=>classes.get(p.class_id)?.grade_level>=lo&&classes.get(p.class_id)?.grade_level<=hi&&(!profilePairs||profilePairs.has(token(p)))):[];
      const id=globalThis.crypto?.randomUUID?.()||`area_${Date.now()}_${Math.random().toString(36).slice(2,9)}`;
      const suffix=lo?` ${lo}–${hi}`:'';
      e.data.areas.push({id,name_ru:lo?(mp?.name||(lo===1?'Начальная школа':'Предметное направление'))+suffix:'',name_kk:lo?(mp?.name||(lo===1?'Бастауыш мектеп':'Пәндік бағыт'))+suffix:'',report_codes:[...codes],pairs:chosen});
      // Reveal the new card even when an earlier area contains hundreds of pairs.
      // Collapsing the earlier selectors changes presentation only, never their data.
      e.open.clear();e.open.add(id);e.focusAreaId=id;e.editId=id;e.notice='added';
      draw();update(root,e);
    };
    tools.append(button(t('Добавить область','Ауқым қосу'),()=>add()),button(t('Заготовка 1–4','1–4 үлгісі'),()=>add(1,4)),button(t('Заготовка 5–11','5–11 үлгісі'),()=>add(5,11)));advanced.append(tools);
    const feedback=el('p');feedback.setAttribute('role','status');feedback.setAttribute('aria-live','polite');
    feedback.dataset.areaFeedback='';
    if(e.notice==='added')feedback.textContent=t('Область добавлена. Укажите название и выберите предметы и классы.','Ауқым қосылды. Атауын енгізіп, пәндер мен сыныптарды таңдаңыз.');
    if(e.notice==='limit')feedback.textContent=t('Можно добавить не более 50 областей. Отредактируйте имеющиеся области.','50 ауқымнан артық қосуға болмайды. Бар ауқымдарды өңдеңіз.');
    if(e.notice)feedback.style.color=e.notice==='limit'?'#b42318':'#067647';
    e.host.append(feedback);
    advanced.append(el('p',t('Заготовка использует текущие предметы, классы и выбранный методический профиль. Проверьте состав и название. Одна пара «предмет — класс» может входить только в одну область каждого типа отчёта.','Үлгі ағымдағы пәндерді, сыныптарды және таңдалған әдістемелік бейінді қолданады. Құрамы мен атауын тексеріңіз. «Пән — сынып» жұбы әр есеп түрінің бір ауқымына ғана кіреді.')));
    if(!codes.length)e.host.append(el('p',t('Выберите качество знаний или обобщённый анализ либо выключите объединение.','Білім сапасын не жалпылама талдауды таңдаңыз немесе біріктіруді өшіріңіз.')));
    e.data.areas.forEach(a=>{
      if(window.ReportAreaPlanner && a.id!==e.editId)return;
      const card=el('article');card.dataset.reportAreaId=a.id;card.style.cssText='scroll-margin-top:120px;margin-top:14px;padding:14px;border:1px solid #dbe3ef;border-radius:10px';
      const header=el('div');header.style.cssText='display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between';
      const title=el('strong',(ru?a.name_ru||a.name_kk:a.name_kk||a.name_ru)||t('Новая область','Жаңа ауқым'));
      header.append(title,button(t('Убрать область','Ауқымды алып тастау'),()=>{e.data.areas=e.data.areas.filter(item=>item.id!==a.id);e.open.delete(a.id);e.editId=null;e.notice=null;update(root,e);draw();},true));card.append(header);
      const names=el('div');names.style.cssText='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:12px 0';
      [['name_ru','Название на русском'],['name_kk','Қазақша атауы']].forEach(([key,label])=>{
        const field=el('label',label),text=el('input');text.type='text';text.value=a[key];text.maxLength=180;text.style.width='100%';
        text.addEventListener('input',()=>{a[key]=text.value;title.textContent=(ru?a.name_ru||a.name_kk:a.name_kk||a.name_ru)||t('Новая область','Жаңа ауқым');update(root,e);});field.append(text);names.append(field);
      });card.append(names);
      const reportBox=el('div');
      Array.from(new Set([...codes,...a.report_codes])).forEach(code=>reportBox.append(checkbox((labels[code]||code)+(codes.includes(code)?'':t(' (не выбран в параметрах)',' (параметрлерде таңдалмаған)')),a.report_codes.includes(code),checked=>{a.report_codes=checked?Array.from(new Set([...a.report_codes,code])):a.report_codes.filter(c=>c!==code);update(root,e);})));
      card.append(reportBox);
      const invalid=a.pairs.filter(p=>!allowed.has(token(p)));
      if(invalid.length){
        const warning=el('p',t(`Недоступных пар: ${invalid.length}. Параметры изменились. Исправьте состав перед сохранением.`,`Қолжетімсіз жұптар: ${invalid.length}. Параметрлер өзгерді. Сақтамас бұрын құрамын түзетіңіз.`));warning.style.color='#b42318';
        card.append(warning,button(t('Убрать недоступные пары','Қолжетімсіз жұптарды алып тастау'),()=>{a.pairs=a.pairs.filter(p=>allowed.has(token(p)));update(root,e);draw();}));
      }
      const details=el('details');details.open=e.open.has(a.id);const summary=el('summary');
      const caption=()=>{summary.textContent=t(`Предметы и классы · выбрано пар: ${a.pairs.length}`,`Пәндер мен сыныптар · таңдалған жұптар: ${a.pairs.length}`);};caption();details.append(summary);
      const pairBox=el('div');details.append(pairBox);let populated=false;
      const populate=()=>{
        if(populated)return;populated=true;
        catalog.subjects.forEach(s=>{
          const available=Array.from(unique.values()).filter(p=>p.subject_id===s.id);if(!available.length)return;
          const block=el('div');block.style.cssText='padding:10px 0;border-bottom:1px solid #edf0f5';block.append(el('strong',ru?s.name_ru||s.name_kz:s.name_kz||s.name_ru));block.append(el('br'));
          available.forEach(p=>block.append(checkbox(classes.get(p.class_id)?.name||String(p.class_id),a.pairs.some(v=>token(v)===token(p)),checked=>{
            a.pairs=a.pairs.filter(v=>token(v)!==token(p));if(checked)a.pairs.push(p);caption();update(root,e);
          })));pairBox.append(block);
        });
        if(!unique.size)pairBox.append(el('p',t('Сначала выберите предметы и классы в параметрах выше.','Алдымен жоғарыдағы параметрлерде пәндер мен сыныптарды таңдаңыз.')));
      };
      details.addEventListener('toggle',()=>{if(details.open){e.open.add(a.id);populate();}else e.open.delete(a.id);});if(details.open)populate();card.append(details);e.host.append(card);
    });
    const focusId=e.focusAreaId;e.focusAreaId=null;
    if(focusId){
      const card=Array.from(e.host.querySelectorAll('[data-report-area-id]')).find(n=>n.dataset.reportAreaId===focusId);
      if(card){card.scrollIntoView?.({block:'start',behavior:'auto'});card.querySelector('input[type="text"]')?.focus({preventScroll:true});}
    }
    update(root,e,false);
  }
  window.ReportAreaEditor={refresh,data:root=>root._reportAreaEditor?.data};
})();
