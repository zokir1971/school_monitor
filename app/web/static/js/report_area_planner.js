/* Simple report list; the existing editor remains the precise composition editor. */
(() => {
  'use strict';
  const key = p => `${p.subject_id}:${p.class_id}`;
  const clone = x => JSON.parse(JSON.stringify(x));
  const id = () => globalThis.crypto?.randomUUID?.() || `area_${Date.now()}_${Math.random().toString(36).slice(2,9)}`;
  const signature = a => [...a.report_codes].sort().join(',')+'|'+a.pairs.map(key).sort().join(',');
  function render(c) {
    const {root,e,catalog,codes,unique,classes,ru,draw,update,el,button,checkbox}=c;
    const t=(a,b)=>ru?a:b, subjects=new Map(catalog.subjects.map(s=>[s.id,s]));
    e.selected ||= new Set();e.undo ||= [];
    if(e.data.scheme_revision===undefined)e.data.scheme_revision=catalog.area_scheme_revision||0;
    e.data.coverage_exclusions ||= [];
    e.data.coverage_version=1;
    const box=el('div');box.style.cssText='margin:12px 0';
    if(e.overview?.parentNode===e.host)e.overview.replaceWith(box);else e.host.append(box);
    e.overview=box;e.syncOverview=()=>render(c);
    const occupied=new Set(),duplicates=new Set(),universe=new Map();
    codes.forEach(code=>unique.forEach(p=>universe.set(code+'|'+key(p),{report_code:code,...p})));
    e.data.areas.forEach(a=>a.report_codes.forEach(code=>a.pairs.forEach(p=>{const k=code+'|'+key(p);if(occupied.has(k))duplicates.add(k);occupied.add(k);})));
    e.data.coverage_exclusions=e.data.coverage_exclusions.filter(p=>universe.has(p.report_code+'|'+key(p))&&!occupied.has(p.report_code+'|'+key(p)));
    const excluded=new Set(e.data.coverage_exclusions.map(p=>p.report_code+'|'+key(p)));
    const missing=[...universe].filter(([k])=>!occupied.has(k)&&!excluded.has(k)).map(([,p])=>p);
    const snapshot=()=>{e.undo.push(clone({enabled:e.data.enabled,areas:e.data.areas,exclusions:e.data.coverage_exclusions}));if(e.undo.length>10)e.undo.shift();};
    const commit=(notice='prepared')=>{e.notice=notice;e.selected.clear();e.editId=null;e.open.clear();update(root,e);draw();};
    const candidates=(source,onlyMissing)=>{
      const wanted=onlyMissing?new Set(missing.map(p=>p.report_code+'|'+key(p))):new Set(universe.keys());
      const prepared=[];
      (source||[]).forEach(a=>{
        a.report_codes.filter(code=>codes.includes(code)).forEach(code=>{
          const pairs=a.pairs.filter(p=>wanted.has(code+'|'+key(p)));
          if(!pairs.length)return;
          const item={...clone(a),report_codes:[code],pairs};
          item.id=e.data.areas.find(old=>signature(old)===signature(item))?.id||id();prepared.push(item);
          pairs.forEach(p=>wanted.delete(code+'|'+key(p)));
        });
      });
      // Older catalog data without suggestions still gets one row per subject/type.
      const rest=new Map();
      wanted.forEach(k=>{const p=universe.get(k);const g=p.report_code+'|'+p.subject_id;if(!rest.has(g))rest.set(g,[]);rest.get(g).push(p);});
      rest.forEach(list=>{const s=subjects.get(list[0].subject_id);prepared.push({id:id(),name_ru:s?.name_ru||s?.name_kz||String(list[0].subject_id),name_kk:s?.name_kz||s?.name_ru||String(list[0].subject_id),report_codes:[list[0].report_code],pairs:list.map(p=>({subject_id:p.subject_id,class_id:p.class_id}))});});
      return prepared;
    };
    const prepare=(source,append=false)=>{
      const prepared=candidates(source,append),next=append?[...e.data.areas,...prepared]:prepared;
      if(!next.length){e.notice='empty';draw();return;}
      if(next.length>50){e.notice='limit';draw();return;}
      snapshot();e.data.enabled=true;e.data.areas=next;
      if(!append)e.data.coverage_exclusions=[];
      commit();
    };
    const tools=el('div');tools.style.cssText='display:flex;flex-wrap:wrap;gap:8px;align-items:center';box.append(tools);
    const suggested=catalog.area_suggestions||catalog.area_defaults;
    if(!e.data.enabled||!e.data.areas.length)tools.append(button(t('Подготовить отчёты автоматически','Есептерді автоматты дайындау'),()=>prepare(suggested)));
    else {
      if(missing.length)tools.append(button(t('Добавить неохваченные','Қамтылмағандарды қосу'),()=>prepare(suggested,true)));
      if(catalog.area_scheme_revision)tools.append(button(t('Применить школьную схему','Мектеп сызбасын қолдану'),()=>prepare(suggested)));
      tools.append(button(t('Стандартная схема','Стандартты сызба'),()=>prepare(catalog.area_defaults)));
    }
    if(e.undo.length)tools.append(button(t('Отменить изменение списка','Тізім өзгерісін болдырмау'),()=>{const old=e.undo.pop();e.data.enabled=old.enabled;e.data.areas=old.areas;e.data.coverage_exclusions=old.exclusions;commit('restored');}));
    if(!e.data.enabled){e.data.save_school_scheme=false;if(e.notice==='limit')box.append(el('p',t('Получилось больше 50 областей. Сузьте выбор или настройте объединение вручную.','50 ауқымнан артық шықты. Таңдауды тарылтыңыз немесе біріктіруді қолмен реттеңіз.')));if(e.notice==='empty')box.append(el('p',t('Сначала выберите предметы, классы и табличный отчёт.','Алдымен пәндерді, сыныптарды және кестелік есепті таңдаңыз.')));return;}
    const messages={prepared:t('Список отчётов подготовлен. Проверьте состав и сохраните изменения.','Есептер тізімі дайындалды. Құрамын тексеріп, өзгерістерді сақтаңыз.'),restored:t('Предыдущий список восстановлен.','Алдыңғы тізім қалпына келтірілді.'),different:t('Объединяйте строки одного типа отчёта.','Бір есеп түрінің жолдарын біріктіріңіз.'),choose:t('Отметьте нужные строки слева.','Сол жақтан қажетті жолдарды белгілеңіз.'),empty:t('Сначала выберите предметы, классы и табличный отчёт.','Алдымен пәндерді, сыныптарды және кестелік есепті таңдаңыз.'),excluded:t('Перечисленные пары явно исключены только из этой задачи. Их можно вернуть.','Көрсетілген жұптар тек осы тапсырмадан анық шығарылды. Оларды қайтаруға болады.')};
    if(messages[e.notice]){const note=el('p',messages[e.notice]);note.setAttribute('role','status');box.append(note);}
    const coverage=el('p');coverage.dataset.areaCoverage='';coverage.setAttribute('role','status');
    if(missing.length)coverage.textContent=t(`Не охвачено: ${missing.length} пар «тип отчёта — предмет — класс».`,`Қамтылмаған «есеп түрі — пән — сынып» жұптары: ${missing.length}.`);
    else if(excluded.size)coverage.textContent=t(`Неохваченных пар нет. Явно исключено из этой задачи: ${excluded.size}.`,`Қамтылмаған жұптар жоқ. Осы тапсырмадан анық шығарылғаны: ${excluded.size}.`);
    else coverage.textContent=t('Все выбранные предметы и классы охвачены.','Барлық таңдалған пәндер мен сыныптар қамтылды.');
    coverage.style.color=missing.length?'#b42318':'#067647';box.append(coverage);
    if(duplicates.size){const warning=el('p',t('Есть повторяющиеся пары в областях одного типа отчёта. Исправьте состав.','Бір есеп түрінің ауқымдарында қайталанатын жұптар бар. Құрамын түзетіңіз.'));warning.style.color='#b42318';box.append(warning);}
    const describe=(pairs,full=false)=>{
      const grouped=new Map();pairs.forEach(p=>{if(!grouped.has(p.subject_id))grouped.set(p.subject_id,[]);grouped.get(p.subject_id).push(p.class_id);});
      return [...grouped].map(([sid,ids])=>{const s=subjects.get(sid),name=ru?s?.name_ru||s?.name_kz:s?.name_kz||s?.name_ru;
        const values=full?ids.map(cid=>classes.get(cid)?.name||String(cid)):[...new Set(ids.map(cid=>classes.get(cid)?.grade_level).filter(Boolean))].sort((a,b)=>a-b);
        return (name||sid)+': '+values.join(', ')+(full?'':t(` (${ids.length} кл.)`,` (${ids.length} сын.)`));}).join('; ');
    };
    if(missing.length){
      const details=el('details'),summary=el('summary',t('Показать неохваченные предметы и классы','Қамтылмаған пәндер мен сыныптарды көрсету'));details.append(summary);
      codes.forEach(code=>{const pairs=missing.filter(p=>p.report_code===code);if(pairs.length)details.append(el('p',(c.flow.report_labels?.[code]?.[ru?'ru':'kk']||code)+' · '+describe(pairs,true)));});
      details.append(button(t('Не учитывать перечисленное в этой задаче','Көрсетілгендерді осы тапсырмада есепке алмау'),()=>{snapshot();e.data.coverage_exclusions.push(...missing);commit('excluded');}));box.append(details);
    }
    if(excluded.size){const details=el('details');details.append(el('summary',t('Явно исключённые пары','Анық шығарылған жұптар')));codes.forEach(code=>{const ps=e.data.coverage_exclusions.filter(p=>p.report_code===code);if(ps.length)details.append(el('p',(c.flow.report_labels?.[code]?.[ru?'ru':'kk']||code)+' · '+describe(ps,true)));});details.append(button(t('Вернуть исключённое','Шығарылғандарды қайтару'),()=>{snapshot();e.data.coverage_exclusions=[];commit();}));box.append(details);}
    const selected=()=>e.data.areas.filter(a=>e.selected.has(a.id));
    const merge=()=>{
      const picked=selected();if(picked.length<2){e.notice='choose';draw();return;}
      if(new Set(picked.map(a=>[...a.report_codes].sort().join(','))).size!==1){e.notice='different';draw();return;}
      snapshot();const first=clone(picked[0]);first.name_ru='Объединённый отчёт';first.name_kk='Біріктірілген есеп';
      first.pairs=[...new Map(picked.flatMap(a=>a.pairs).map(p=>[key(p),p])).values()];
      e.data.areas=e.data.areas.filter(a=>!e.selected.has(a.id));e.data.areas.push(first);commit();e.editId=first.id;e.focusAreaId=first.id;e.open.add(first.id);draw();
    };
    const split=kind=>{
      const picked=selected();if(!picked.length){e.notice='choose';draw();return;}
      const next=[];
      e.data.areas.forEach(a=>{
        if(!e.selected.has(a.id)){next.push(a);return;}
        const groups=new Map();a.pairs.forEach(p=>{const grade=classes.get(p.class_id)?.grade_level;const group=kind==='subject'?p.subject_id:grade<=4?'1–4':grade<=9?'5–9':'10–11';if(!groups.has(group))groups.set(group,[]);groups.get(group).push(p);});
        if(groups.size<=1){next.push(a);return;}
        [...groups].forEach(([g,pairs],index)=>{const s=subjects.get(g);next.push({...clone(a),id:index?id():a.id,pairs,
          name_ru:kind==='subject'?(s?.name_ru||s?.name_kz||String(g)):a.name_ru+' · '+g,
          name_kk:kind==='subject'?(s?.name_kz||s?.name_ru||String(g)):a.name_kk+' · '+g});});
      });
      if(next.length>50){e.notice='limit';draw();return;}snapshot();e.data.areas=next;commit();
    };
    const actions=el('div');actions.style.cssText='display:flex;gap:8px;flex-wrap:wrap;margin:12px 0';
    actions.append(button(t('Объединить выбранные','Таңдалғандарды біріктіру'),merge),button(t('Разделить по предметам','Пәндер бойынша бөлу'),()=>split('subject')),button(t('Разделить по ступеням','Сатылар бойынша бөлу'),()=>split('stage')));box.append(actions);
    const wrap=el('div');wrap.style.overflowX='auto';const table=el('table');table.style.cssText='width:100%;min-width:620px;border-collapse:collapse';table.dataset.areaList='';
    const head=el('thead'),hr=el('tr');['',t('Отчёт','Есеп'),t('Состав','Құрамы'),t('Действие','Әрекет')].forEach(label=>{const th=el('th',label);th.style.cssText='text-align:left;padding:9px;background:#f1f5fb';hr.append(th);});head.append(hr);table.append(head);
    const body=el('tbody');
    e.data.areas.forEach(a=>{
      const row=el('tr');row.dataset.areaRow=a.id;
      const select=el('td');select.append(checkbox('',e.selected.has(a.id),checked=>checked?e.selected.add(a.id):e.selected.delete(a.id)));select.querySelector('input').setAttribute('aria-label',t('Выбрать отчёт: ','Есепті таңдау: ')+(ru?a.name_ru:a.name_kk));
      const name=el('td');name.append(el('strong',(ru?a.name_ru||a.name_kk:a.name_kk||a.name_ru)||t('Без названия','Атаусыз')));name.append(el('p',a.report_codes.map(code=>c.flow.report_labels?.[code]?.[ru?'ru':'kk']||code).join(', ')));
      const composition=el('td',describe(a.pairs));const action=el('td');action.append(button(t('Изменить состав','Құрамын өзгерту'),()=>{e.editId=a.id;e.focusAreaId=a.id;e.open.clear();e.open.add(a.id);draw();}));row.append(select,name,composition,action);[...row.children].forEach(td=>td.style.cssText='padding:9px;border-bottom:1px solid #dbe3ef;vertical-align:top');body.append(row);
    });table.append(body);wrap.append(table);box.append(wrap);
    const layout=el('div');layout.style.cssText='margin:14px 0;padding:12px;background:#f1f5fb;border-radius:8px';
    layout.append(checkbox(t('Сохранить эту структуру как школьную схему для следующих задач','Осы құрылымды келесі тапсырмаларға мектеп сызбасы ретінде сақтау'),!!e.data.save_school_scheme,checked=>{e.data.save_school_scheme=checked;update(root,e);}));
    layout.append(el('p',t('Сохраняется кнопкой «Сохранить изменения». Схема группирует по предмету, параллели, языку обучения и профилю. В следующих задачах используются только выбранные там классы. Схему сохраняет администратор или основной исполнитель; она не назначает сотрудников.','«Өзгерістерді сақтау» түймесімен сақталады. Сызба пән, сынып деңгейі, оқыту тілі және бейін бойынша топтайды. Келесі тапсырмаларда тек сол жерде таңдалған сыныптар қолданылады. Сызбаны әкімші не негізгі орындаушы сақтайды; қызметкерлер автоматты тағайындалмайды.')));box.append(layout);
  }
  window.ReportAreaPlanner={render};
})();
