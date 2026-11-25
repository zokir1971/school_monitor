"""Reading, document inventory and final reference in existing execution documents.

Only domain fields live here; authorization, revisions, signing and file lifecycle
remain in the shared report controller/document service. SQL lives in repositories.
"""
import calendar
import math
import re
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from app.modules.reports.assessment_report_types import REPORT_TYPES
from app.modules.reports.repositories import assessment_report_repo as documents
from app.modules.reports.repositories import structured_report_repo as repo
from app.modules.reports.services.assessment_report_service import QualityReportError, integer, value, json_value, is_snapshot, checked_document

PAGE_SIZE=25
DOCUMENT_PAGE_SIZE=10
CATEGORIES={
 'school_strategy':dict(ru='Перспективный план развития школы',kk='Мектептің перспективалық даму жоспары'),
 'school_annual':dict(ru='Годовой план школы',kk='Мектептің жылдық жоспары'),
 'school_control':dict(ru='План внутришкольного контроля',kk='Мектепішілік бақылау жоспары'),
 'education_program':dict(ru='Учебный / воспитательный план',kk='Оқу / тәрбие жоспары'),
 'policy':dict(ru='Локальные акты и положения',kk='Жергілікті актілер мен ережелер'),
 'department_plan':dict(ru='План подразделения / методического объединения',kk='Бөлімнің / әдістемелік бірлестіктің жоспары'),
 'ktp':dict(ru='Календарно-тематический план',kk='Күнтізбелік-тақырыптық жоспар'),
 'ksp':dict(ru='Краткосрочный план урока',kk='Сабақтың қысқа мерзімді жоспары'),
 'employee_plan':dict(ru='План сотрудника (психолог, социальный педагог и др.)',kk='Қызметкердің жоспары (психолог, әлеуметтік педагог және т.б.)'),
 'other':dict(ru='Другой документ школы',kk='Мектептің басқа құжаты')}
STATES={
 'pending':dict(ru='Не проверено',kk='Тексерілмеген'), 'present':dict(ru='Участвовал',kk='Қатысты'),
 'absent':dict(ru='Отсутствовал',kk='Қатыспады'), 'excused':dict(ru='Освобождён',kk='Босатылған'),
 'yes':dict(ru='Есть',kk='Бар'), 'no':dict(ru='Нет',kk='Жоқ'),
 'not_checked':dict(ru='Не проверено',kk='Тексерілмеген'), 'complies':dict(ru='Соответствует',kk='Сәйкес келеді'),
 'non_compliant':dict(ru='Не соответствует',kk='Сәйкес келмейді'), 'not_applicable':dict(ru='Не применяется',kk='Қолданылмайды'),
 'completed':dict(ru='Завершён',kk='Аяқталған'), 'waived':dict(ru='Освобождён от выполнения',kk='Орындаудан босатылған')}


def text(params,key,limit=2000,default=''):
    raw=str(params.get(key,default) or '').strip()
    if len(raw)>limit:raise QualityReportError(f'Поле «{key}»: не более {limit} символов. / «{key}» өрісі: {limit} таңбадан аспайды.',field=key)
    return raw


def day(raw,field):
    try:return date.fromisoformat(str(raw))
    except (ValueError,TypeError):raise QualityReportError('Укажите корректную дату. / Дұрыс күнді көрсетіңіз.',field=field)


def number(raw,key,*,minimum=0,maximum=100000,whole=False,required=False):
    if raw in ('',None):
        if required:raise QualityReportError('Заполните числовой показатель. / Сандық көрсеткішті толтырыңыз.',field=key)
        return None
    try:result=Decimal(str(raw).replace(',','.'))
    except InvalidOperation:raise QualityReportError('Введите число. / Сан енгізіңіз.',field=key)
    if not result.is_finite() or not minimum<=result<=maximum or (whole and result!=result.to_integral_value()):
        raise QualityReportError(f'Допустимое значение: {minimum}–{maximum}. / Рұқсат етілген мән: {minimum}–{maximum}.',field=key)
    return int(result) if whole else result




def blank_document(index):
    return dict(key=index,title='',category='other',period='',owner_id='',owner_name='',presence='not_checked',compliance='not_checked',note='',evidence='',source_document_id='')


async def load(db,user,task_id,selected_id,params,*,lock=False,report_code):
    if not user.school_id or not user.staff_member_id:raise QualityReportError('Требуется связь со школой и сотрудником. / Мектеппен және қызметкермен байланыс қажет.')
    context=await documents.context(db,task_id=task_id,selected_id=selected_id,user=user,lock=lock,report_code=report_code)
    if context is None:raise QualityReportError('Отчёт не найден или недоступен. / Есеп табылмады немесе қолжетімсіз.')
    doc=await documents.document(db,selected_id,task_id=task_id,report_code=report_code)
    saved=(doc or {}).get('schema_json') or {}
    if saved and not is_snapshot(saved,report_code):saved={}
    from app.core.feature_flags import assessment_enabled,snapshot_has_assessment
    from app.core.feature_access import FeatureUnavailable
    if not assessment_enabled() and snapshot_has_assessment(saved) and doc and value(doc['status']) not in ('draft','rejected'):raise FeatureUnavailable()
    year=integer(str(context['academic_year'])[:4]);month=context['month'] or 9;period_year=year+(month<8)
    default_from=date(period_year,month,1).isoformat();default_to=date(period_year,month,calendar.monthrange(period_year,month)[1]).isoformat()
    page=dict(context=context,document=dict(doc) if doc else None,scope=dict(mode='complex',teacher_name=None),filters=dict(year=year),
        classes=[],subjects=[],candidates=[],selected=[],overflow=False,form_values={},entry_rows=[],all_entries=[],categories=CATEGORIES,states=STATES)
    if doc and value(doc['status']) not in ('draft','rejected'):
        size=DOCUMENT_PAGE_SIZE if report_code=='document_analysis' else PAGE_SIZE
        count=max([e.get('key',0) for e in saved.get('entries',[])],default=0)
        page['page_count']=max(1,math.ceil(count/size))
        page['entry_page']=min(page['page_count'],max(1,integer(params.get('entry_page'),1)))
        return page  # Finalized data render directly from the snapshot without new source reads.
    form=dict(saved.get('form') or {})
    form.update({k:str(v) for k,v in params.items() if k in ('check_date','criteria','threshold','text_title','reading_language','date_from','date_to','purpose')})
    form.setdefault('check_date',default_to);form.setdefault('date_from',default_from);form.setdefault('date_to',default_to)
    if report_code=='analytical_reference':
        form.setdefault('purpose',(context.get('goal') or '')[:2000])
        if not saved:
            form['date_from']=str(context.get('planned_start') or form['date_from'])
            form['date_to']=str(context.get('planned_end') or form['date_to'])
    form.setdefault('reading_language','kk');page['structured_form']=form
    for key in ('conclusion','recommendations','document_language','analysis_text'):
        if key in params:page['form_values'][key]=str(params[key])
    page['entry_page']=max(1,integer(params.get('entry_page'),1))
    if report_code=='reading_speed_table':
        classes=await repo.classes(db,user.school_id,year)
        if len(classes)>1000:raise QualityReportError('Уточните область проверки: слишком много классов. / Тексеру ауқымын нақтылаңыз: сыныптар тым көп.')
        bounds=context.get('algorithm_parameters') or {};kind=context['target_kind'];raw=str(context['target_value'])
        if bounds.get('version')==2:classes=[c for c in classes if c['id'] in bounds.get('class_ids',[])]
        if kind=='class':classes=[c for c in classes if raw in (str(c['id']),c['name'])]
        elif kind in ('parallel','parallel_class'):classes=[c for c in classes if str(c['grade_level'])==raw]
        else:raise QualityReportError('Для чтения выберите класс или параллель в алгоритме. / Оқу үшін алгоритмде сыныпты немесе сынып деңгейін таңдаңыз.')
        if not classes or any(c['grade_level'] not in range(1,5) for c in classes):raise QualityReportError('Скорость чтения: выберите 1–4 классы. / Оқу жылдамдығы: 1–4 сыныптарды таңдаңыз.')
        page['classes']=classes
        if saved:
            if form['check_date']!=saved['form']['check_date']:raise QualityReportError('Состав учеников уже зафиксирован. Для другой даты создайте отдельный отчёт. / Оқушылар құрамы бекітілген. Басқа күн үшін бөлек есеп жасаңыз.',field='check_date')
            entries=deepcopy(saved['entries'])
        else:entries=await repo.roster(db,user.school_id,year,[c['id'] for c in classes],day(form['check_date'],'check_date'))
        if len(entries)>2000:raise QualityReportError('В одном отчёте не более 2000 учеников. Выберите конкретный класс. / Бір есепте 2000 оқушыдан аспайды. Нақты сыныпты таңдаңыз.')
        if len({row['id'] for row in entries})!=len(entries):raise QualityReportError('Проверьте пересекающиеся зачисления учеников; выберите один класс. / Оқушылардың қабаттасқан қабылдануын тексеріңіз; бір сыныпты таңдаңыз.')
        for index,row in enumerate(entries):row['key']=index+1
        page['page_size']=PAGE_SIZE
    elif report_code=='document_analysis':
        if context['target_kind'] not in ('documentation','complex'):raise QualityReportError('Выберите документы как объект проверки в алгоритме. / Алгоритмде тексеру нысаны ретінде құжаттарды таңдаңыз.')
        staff=await repo.staff(db,user.school_id)
        if len(staff)>2000:raise QualityReportError('В школе более 2000 сотрудников. Уточните справочник. / Мектепте 2000 қызметкерден артық. Анықтамалықты нақтылаңыз.')
        page['staff']=staff;entries=deepcopy(saved.get('entries',[]));page['page_size']=DOCUMENT_PAGE_SIZE
        last=max([e['key'] for e in entries],default=0)
        page['entry_page']=min(page['entry_page'],math.ceil(last/DOCUMENT_PAGE_SIZE)+1,100)
        keys={e['key'] for e in entries};start=(page['entry_page']-1)*DOCUMENT_PAGE_SIZE
        entries.extend(blank_document(key) for key in range(start+1,start+DOCUMENT_PAGE_SIZE+1) if key not in keys)
        entries.sort(key=lambda row:row['key'])
    else:
        page['source_reports']=await repo.evidence(db,user.school_id,task_id)
        if not assessment_enabled():page['source_reports']=[row for row in page['source_reports'] if row['code']!='knowledge_quality_table' and not (row['code'] in ('class_summary','teacher_analysis') and row.get('totals'))]
        if len(page['source_reports'])>2000:raise QualityReportError('Слишком много отчётов в задаче. Разделите область контроля. / Тапсырмада есептер тым көп. Бақылау ауқымын бөліңіз.')
        entries=[];page['page_size']=PAGE_SIZE
        from app.modules.reports.services.final_reference_assembly import fingerprint
        current_entries,_=source_snapshot(page,False)
        page['source_fingerprint']=fingerprint(current_entries,saved.get('source_fingerprint_version',1))
        previous_fingerprint=saved.get('source_fingerprint') or (fingerprint(saved['entries']) if saved else '')
        page['sources_changed']=bool(previous_fingerprint and previous_fingerprint!=page['source_fingerprint'])
    page['page_count']=max(1,math.ceil(max([e.get('key',0) for e in entries],default=0)/page['page_size']))
    if report_code!='document_analysis':page['entry_page']=min(page['entry_page'],page['page_count'])
    start=(page['entry_page']-1)*page['page_size'];end=start+page['page_size']
    # Document keys can have gaps after explicit deletion; pages are fixed key ranges.
    visible=[e for e in entries if start<e['key']<=end]
    posted=params.get('structured_form_version')=='1'
    if posted:
        allowed={e['key'] for e in visible}
        for key in params:
            match=re.match(r'^entry_([0-9]+)_',str(key))
            if match and int(match[1]) not in allowed:raise QualityReportError('Строка не входит в текущую страницу. Обновите отчёт. / Жол ағымдағы бетке кірмейді. Есепті жаңартыңыз.')
        fields=('state','words','errors','seconds','comprehension','note') if report_code=='reading_speed_table' else ('title','category','period','owner_id','presence','compliance','note','evidence','source_document_id','delete')
        for row in visible:
            prefix='entry_'+str(row['key'])+'_'
            row.update({key:str(params.get(prefix+key) or '') for key in fields})
    page.update(all_entries=entries,entry_rows=visible)
    return page


def reading_snapshot(page,completing):
    form=page['structured_form'];entries=[];speeds=[];below=0;counts=dict(present=0,absent=0,excused=0,pending=0)
    threshold=number(form.get('threshold'),'threshold',minimum=1,maximum=1000,required=completing)
    if completing and not str(form.get('criteria') or '').strip():raise QualityReportError('Укажите критерий чтения и его основание. / Оқу критерийі мен оның негіздемесін көрсетіңіз.',field='criteria')
    if form['reading_language'] not in ('ru','kk'):raise QualityReportError('Выберите язык чтения. / Оқу тілін таңдаңыз.',field='reading_language')
    for row in page['all_entries']:
        row=dict(row);prefix='entry_'+str(row['key'])+'_';state=row['state'] or 'pending'
        if state not in counts:raise QualityReportError('Выберите состояние ученика. / Оқушының күйін таңдаңыз.',field=prefix+'state')
        counts[state]+=1;row.update(state=state,wpm=None,below=None)
        if state=='pending' and completing:raise QualityReportError(f"{row['class_name']} · {row['name']}: не проверено (страница {(row['key']-1)//PAGE_SIZE+1}). / {row['class_name']} · {row['name']}: тексерілмеген (бет {(row['key']-1)//PAGE_SIZE+1}).",field=prefix+'state')
        if state=='present':
            words=number(row['words'],prefix+'words',whole=True,maximum=10000,required=completing)
            errors=number(row['errors'],prefix+'errors',whole=True,maximum=10000,required=completing)
            seconds=number(row['seconds'],prefix+'seconds',minimum=1,maximum=3600,required=completing)
            if words is not None and errors is not None and errors>words:raise QualityReportError(row['name']+': число ошибок превышает число слов. / Қателер саны сөздер санынан артық.',field=prefix+'errors')
            if words is not None and errors is not None and seconds is not None:
                speed=(Decimal(words-errors)*60/seconds).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
                row['wpm']=speed;speeds.append(speed)
                if threshold is not None:row['below']=speed<threshold;below+=int(row['below'])
        if row.get('comprehension') not in ('not_checked','yes','no',''):raise QualityReportError('Проверьте понимание текста. / Мәтінді түсінуді тексеріңіз.',field=prefix+'comprehension')
        if len(row.get('note',''))>2000:raise QualityReportError('Сократите примечание ученика. / Оқушы ескертпесін қысқартыңыз.',field=prefix+'note')
        entries.append(row)
    if not entries:raise QualityReportError('В выбранных классах нет учеников на дату проверки. / Тексеру күні таңдалған сыныптарда оқушы жоқ.')
    summary=dict(**counts,total=len(entries),checked=len(speeds),below=below if threshold is not None else None,
        average_wpm=(sum(speeds)/len(speeds)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP) if speeds else None,check_date=form['check_date'],criteria=form.get('criteria',''),threshold=threshold,
        class_ids=[c['id'] for c in page['classes']],class_names=[c['name'] for c in page['classes']])
    return entries,summary


async def document_snapshot(db,user,page,completing):
    entries=[];pool={s['id']:s for s in page['staff']};old={r['key']:r for r in ((page['document'] or {}).get('schema_json') or {}).get('entries',[])}
    for row in page['all_entries']:
        prefix='entry_'+str(row['key'])+'_'
        if row.get('delete')=='1':continue
        if not row.get('title','').strip():
            if any(str(row.get(k) or '').strip() for k in ('period','owner_id','note','evidence','source_document_id')) or row.get('presence') not in ('','not_checked'):raise QualityReportError('Укажите название документа. / Құжат атауын көрсетіңіз.',field=prefix+'title')
            continue
        result={k:text(row,k,300 if k in ('title','period') else 2000) for k in ('title','period','note','evidence')}
        category=row.get('category') or 'other'
        if category not in CATEGORIES:raise QualityReportError('Выберите вид документа. / Құжат түрін таңдаңыз.',field=prefix+'category')
        owner=integer(row.get('owner_id'));previous=old.get(row['key'],{})
        if owner and owner not in pool and owner!=previous.get('owner_id'):raise QualityReportError('Ответственный сотрудник не найден в школе. / Жауапты қызметкер мектептен табылмады.',field=prefix+'owner_id')
        if completing and category=='employee_plan' and not owner:raise QualityReportError(result['title']+': выберите сотрудника. / Қызметкерді таңдаңыз.',field=prefix+'owner_id')
        try:check=checked_document(row.get('presence') or 'not_checked',row.get('compliance') or 'not_checked',result['note'],completing=completing,prefix=prefix)
        except QualityReportError as exc:
            raise QualityReportError({lang:result['title']+(' (страница ' if lang=='ru' else ' (бет ')+str((row['key']-1)//DOCUMENT_PAGE_SIZE+1)+') — '+exc.messages[lang] for lang in ('ru','kk')},field=exc.field) from exc
        entries.append(dict(result,**{k:v for k,v in check.items() if k!='note'},key=row['key'],category=category,owner_id=owner,
            owner_name=(pool.get(owner) or {}).get('full_name') or (previous.get('owner_name','') if owner else ''),source_document_id=integer(row.get('source_document_id'))))
    if len(entries)>1000:raise QualityReportError('Не более 1000 документов в одном отчёте. / Бір есепте 1000 құжаттан аспайды.')
    if completing and not entries:raise QualityReportError('Добавьте проверенные документы. / Тексерілген құжаттарды қосыңыз.')
    refs=await repo.referenced_documents(db,user.school_id,{r['source_document_id'] for r in entries if r['source_document_id']})
    for row in entries:
        if row['source_document_id'] and row['source_document_id'] not in refs:raise QualityReportError(row['title']+': исходный документ отсутствует или недоступен. / Бастапқы құжат жоқ немесе қолжетімсіз.',field='entry_'+str(row['key'])+'_source_document_id')
        row['source']=refs.get(row['source_document_id'])
    summary=dict(total=len(entries),present=sum(r['presence']=='yes' for r in entries),missing=sum(r['presence']=='no' for r in entries),
        complies=sum(r['compliance']=='complies' for r in entries),non_compliant=sum(r['compliance']=='non_compliant' for r in entries),
        pending=sum(r['presence']=='not_checked' or (r['presence']=='yes' and r['compliance']=='not_checked') for r in entries))
    return entries,summary


def source_snapshot(page,completing):
    entries=[]
    from app.core.feature_flags import assessment_enabled,report_enabled
    for source in page['source_reports']:
        if not report_enabled(source['code']):continue
        if not assessment_enabled() and source['code'] in ('class_summary','teacher_analysis') and source.get('totals'):continue
        state='waived' if value(source['assignment_status'])=='waived' else 'completed' if value(source['document_status']) in ('submitted','accepted','approved') else 'pending'
        if completing and state=='pending':raise QualityReportError(f"{source['target_label']} · №{source['selected_id']}: завершите исходный отчёт или оформите освобождение. / Бастапқы есепті аяқтаңыз немесе босатуды рәсімдеңіз.")
        cfg=REPORT_TYPES.get(source['code'],{})
        entries.append(dict(selected_id=source['selected_id'],document_id=source['document_id'],code=source['code'],
            titles={lang:cfg.get('title_'+lang) or source.get('type_label_'+lang) or source['code'] for lang in ('ru','kk')},
            target=source['target_label'],state=state,finding=source.get('finding','') if state=='completed' else '',revision=source['revision'],version=source['version'],submitted_at=source['submitted_at'],
            conclusion_text=(source.get('conclusion_text') or '') if state=='completed' else '',
            recommendations_text=(source.get('recommendations_text') or '') if state=='completed' else '',
            summary=source['summary'] if state=='completed' and isinstance(source.get('summary'),dict) else None,
            totals=[row for row in source['totals'] if isinstance(row,dict)] if state=='completed' and isinstance(source.get('totals'),list) else None,
            score=(source['score'] if source['code']=='lesson_observation' else source['notebook_score']) if state=='completed' else None,
            max_score=(source['max_score'] if source['code']=='lesson_observation' else source['notebook_max']) if state=='completed' else None))
    return entries,dict(total=len(entries),completed=sum(e['state']=='completed' for e in entries),waived=sum(e['state']=='waived' for e in entries),pending=sum(e['state']=='pending' for e in entries))


async def calculate(db,user,page,params,language):
    completing=params.get('action')=='complete';code=page['context']['report_code'];form=page['structured_form']
    assembly={}
    for key in ('criteria','text_title','purpose'):form[key]=text(form,key)
    start=day(form['date_from'],'date_from');end=day(form['date_to'],'date_to')
    if start>end:raise QualityReportError('Начало периода позже окончания. / Кезеңнің басы соңынан кейін.',field='date_to')
    if code=='reading_speed_table':
        if not start<=day(form['check_date'],'check_date')<=end:raise QualityReportError('Дата чтения вне периода проверки. / Оқу күні тексеру кезеңінен тыс.',field='check_date')
        entries,summary=reading_snapshot(page,completing)
    elif code=='document_analysis':entries,summary=await document_snapshot(db,user,page,completing)
    else:
        assembling=params.get('action')=='assemble'
        entries,summary=source_snapshot(page,completing or assembling)
        if (completing or assembling) and not entries:
            raise QualityReportError('В задаче нет исходных отчётов для сборки справки. / Анықтама құрастыруға бастапқы есептер жоқ.')
        from app.modules.reports.services.final_reference_assembly import fingerprint, analysis_text, task_metadata
        previous=((page['document'] or {}).get('schema_json') or {})
        fingerprint_version=2 if assembling else previous.get('source_fingerprint_version',1)
        current_fingerprint=fingerprint(entries,fingerprint_version)
        expected=params.get('source_fingerprint') or previous.get('source_fingerprint')
        if not assembling and expected and expected!=current_fingerprint:
            raise QualityReportError('Исходные отчёты изменились. Нажмите «Собрать / обновить данные отчётов»: введённый текст сохранится. / Бастапқы есептер өзгерді. Есеп деректерін жаңартыңыз: енгізілген мәтін сақталады.')
        if not assembling and completing and previous.get('assembly_version')!=1:
            raise QualityReportError('Сначала соберите и сохраните черновик итогового документа. / Алдымен қорытынды құжат жобасын құрастырып сақтаңыз.')
        narrative=text(params,'analysis_text',30000,default=previous.get('analysis_text',''))
        if assembling and not narrative and 'analysis_text' not in previous:narrative=analysis_text(entries,language)
        defaults=previous.get('source_text_defaults') or {}
        if assembling:
            from app.modules.reports.services.final_reference_assembly import collect_source_texts, merge_source_texts
            defaults=collect_source_texts(entries,language)
            replacements=merge_source_texts(params,previous,defaults)
            params=dict(params,**replacements)
        assembly=dict(assembly_version=1,source_fingerprint=current_fingerprint,source_fingerprint_version=fingerprint_version,
            source_text_defaults=defaults,analysis_text=narrative,task_metadata=task_metadata(page['context']))
        if completing and not text(params,'conclusion',10000):raise QualityReportError('Заполните выводы аналитической справки. / Талдау анықтамасының қорытындысын толтырыңыз.',field='conclusion')
        if completing and not text(params,'recommendations',10000):
            raise QualityReportError('Заполните рекомендации итоговой справки. / Қорытынды анықтаманың ұсынымдарын толтырыңыз.',field='recommendations')
    # Only needed in the preview; authoritative saved pages are rebuilt from this snapshot.
    return json_value(dict(kind='vsk_structured_report',schema_version=1,report_layout_version=166,report_code=code,
        report_titles={lang:REPORT_TYPES[code]['title_'+lang] for lang in ('ru','kk')},language=language,
        created_at=datetime.now(timezone.utc),school_name=page['context']['school_name'],target_label=page['context']['target_label'],
        mode='complex',filters=page['filters'],form=form,entries=entries,summary=summary,rows=[],states=STATES,categories=CATEGORIES,
        conclusion=text(params,'conclusion',10000),recommendations=text(params,'recommendations',10000),**assembly))
