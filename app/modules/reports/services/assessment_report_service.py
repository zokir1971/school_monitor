from app.core.feature_flags import assessment_enabled,snapshot_has_assessment
from app.core.feature_access import ensure_report,FeatureUnavailable
"""Build VSK reports from existing assessment results; no SQL in this module."""
import re
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from app.modules.assessment.repositories import vsk_quality_report_repo as data_repo
from app.modules.reports.repositories import assessment_report_repo as report_repo
from app.modules.reports.assessment_report_types import REPORT_TYPES
from app.modules.reports.rules.control_flow import report_algorithm_bounds
from app.modules.reports.rules.inspection_evidence import class_index, source_rows, group_source_rows
from app.modules.assessment.services.knowledge_quality_calculator import KnowledgeQualityCalculator
from app.modules.assessment.helpers.question_prose_layout import explanation_blocks


class QualityReportError(ValueError):
    def __init__(self,message,*,field=None):
        if isinstance(message,dict):self.messages=message
        else:
            ru,separator,kk=str(message).partition(' / ')
            self.messages={'ru':ru,'kk':kk if separator else ru}
        self.field=field
        super().__init__(' / '.join(dict.fromkeys(self.messages.values())))


def error_message(error,language):
    if error is None:return None
    messages=getattr(error,'messages',None)
    if messages:return messages.get(language) or messages.get('ru') or str(error)
    return QualityReportError(str(error)).messages.get(language,str(error))


def review_error(message,*,teacher=None,section=None,parameter=None,field=None):
    base=QualityReportError(message);labels=[]
    if teacher:labels.append(teacher['name'] if isinstance(teacher,dict) else str(teacher))
    if section:labels.append(INSPECTION_SECTIONS.get(section,section) if isinstance(section,str) else section)
    if parameter:labels.append(parameter)
    return QualityReportError({lang:' — '.join([str(label.get(lang,label.get('ru',''))) if isinstance(label,dict) else str(label) for label in labels]+[base.messages[lang]]) for lang in ('ru','kk')},field=field)


def value(item):
    return getattr(item,'value',item)


def integer(raw,default=None):
    if raw in (None,''):return default
    try:return int(raw)
    except (TypeError,ValueError):raise QualityReportError('Некорректный числовой параметр. / Сандық параметр дұрыс емес.')


def ids(params,key,*,limit=200):
    values=params.getlist(key) if hasattr(params,'getlist') else params.get(key,[])
    if isinstance(values,(str,int)):values=[values]
    result=sorted(set(integer(v) for v in values))
    if any(v is None or v<1 for v in result) or len(result)>limit:
        raise QualityReportError(f'Выберите не более {limit} строк. / {limit} жолдан артық таңдамаңыз.')
    return result


def json_value(obj):
    if isinstance(obj,Decimal):return str(obj)
    if isinstance(obj,(datetime,date)):return obj.isoformat()
    if isinstance(obj,dict):return {k:json_value(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)):return [json_value(v) for v in obj]
    return value(obj)


def target(context,classes,subjects):
    """A report target is authoritative; form fields cannot broaden it."""
    kind=context['target_kind'];raw=context['target_value'];scope=dict(teacher_id=None,subject_id=None,class_id=None,grades=None)
    if kind == 'report_area':
        area=next((a for a in (context.get('algorithm_parameters') or {}).get('report_areas',[]) if a['id']==str(raw)),None)
        if not area:raise QualityReportError('Область отчёта не найдена. / Есеп ауқымы табылмады.')
        scope.update(mode='area')
    elif kind in ('teacher','primary_teacher'):
        scope.update(mode='teacher',teacher_id=integer(raw))
    elif kind=='subject':
        matches=[s['id'] for s in subjects if str(s['id'])==raw or raw in (s['name_ru'],s['name_kz'])]
        if len(matches)!=1:raise QualityReportError('Предмет цели контроля не найден среди завершённых работ. / Бақылау пәні аяқталған жұмыстардан табылмады.')
        scope.update(mode='subject',subject_id=matches[0])
    elif kind=='class':
        matches=[c['id'] for c in classes if str(c['id'])==raw or c['name']==raw]
        if len(matches)!=1:raise QualityReportError('Класс цели контроля не найден. / Бақылау сыныбы табылмады.')
        scope.update(mode='class',class_id=matches[0])
    elif kind in ('parallel','parallel_class'):
        grade=integer(raw)
        if grade not in range(1,13):raise QualityReportError('Проверьте параллель. / Сынып деңгейін тексеріңіз.')
        scope.update(mode='class',grades=[grade])
    elif kind=='class_group' and raw in ('1_4','5_9','10_11'):
        lo,hi=map(int,raw.split('_'));scope.update(mode='class',grades=list(range(lo,hi+1)))
    else:
        # Unknown composite formats must not silently fall back to whole-school scope.
        raise QualityReportError('Для этого объекта контроля требуется уточнение цели: учитель, предмет или класс. / Бақылау нысанын нақтылаңыз: мұғалім, пән немесе сынып.')
    return scope


async def load(db,user,task_id,selected_id,params,*,lock=False,report_code='knowledge_quality_table'):
    ensure_report(report_code)
    if REPORT_TYPES.get(report_code,{}).get('structured'):
        from app.modules.reports.services import structured_report_service
        return await structured_report_service.load(db,user,task_id,selected_id,params,lock=lock,report_code=report_code)
    if report_code not in REPORT_TYPES:raise QualityReportError('Неизвестный тип отчёта. / Белгісіз есеп түрі.')
    if not user.school_id or not user.staff_member_id:
        raise QualityReportError('Пользователь должен быть связан со школой и сотрудником. / Пайдаланушы мектеппен және қызметкермен байланыстырылуы тиіс.')
    context=await report_repo.context(db,task_id=task_id,selected_id=selected_id,user=user,lock=lock,report_code=report_code)
    if context is None:raise QualityReportError('Отчёт не найден или недоступен. / Есеп табылмады немесе қолжетімсіз.')
    raw=context['target_value']
    context['target_labels']={lang:(str(raw)+suffix if context['target_kind'] in ('parallel','parallel_class') else context['target_label'])
        for lang,suffix in [('ru',' класс'),('kk',' сынып')]}
    if report_code=='teacher_analysis' and context['target_kind'] not in ('teacher','primary_teacher'):
        raise QualityReportError('Для анализа работы выберите конкретного учителя в алгоритме. / Жұмысты талдау үшін алгоритмде нақты мұғалімді таңдаңыз.')
    if context['target_kind']=='report_area':
        area=next((a for a in (context.get('algorithm_parameters') or {}).get('report_areas',[]) if a['id']==str(raw)),None)
        if area:context['target_labels']={'ru':area['name_ru'],'kk':area['name_kk']}
    doc=await report_repo.document(db,selected_id)
    saved=(doc or {}).get('schema_json') or {}
    if not assessment_enabled() and snapshot_has_assessment(saved) and doc and value(doc['status']) in ('submitted','approved','accepted'):
        raise FeatureUnavailable()
    if doc and value(doc['status']) in ('submitted','approved','accepted') and is_snapshot(saved,report_code):
        # Frozen view must survive source assessment edits or a teaching-load change.
        return dict(context=context,scope=dict(mode=saved['mode'],teacher_name=saved.get('teacher_name')),
            filters=saved['filters'],classes=[],subjects=[],candidates=[],selected=[],overflow=False,document=dict(doc))
    if not params and doc and is_snapshot(doc['schema_json'] or {},report_code):
        saved=doc['schema_json'];params=dict(saved['filters'],group_ids=[r['group_id'] for r in saved['rows']])
    year=integer(str(context['academic_year'])[:4])
    catalog=None
    if report_code in ('class_summary','teacher_analysis') or (context.get('algorithm_parameters') or {}).get('version') == 2:
        from app.modules.reports.repositories.execution_repo import ExecutionRepo
        catalog=await ExecutionRepo.get_algorithm_catalog(db,month_item_id=task_id,school_id=user.school_id)
        classes,subjects=catalog['classes'],catalog['subjects']
    else:classes,subjects=await data_repo.reference_data(db,user.school_id,year)
    scope=target(context,classes,subjects)
    if scope['teacher_id']:
        name=await data_repo.teacher_name(db,user.school_id,scope['teacher_id'])
        if not name:raise QualityReportError('Учитель не найден в школе. / Мұғалім мектептен табылмады.')
        scope['teacher_name']=name
        if report_code=='teacher_analysis':
            loads=[row for row in catalog['teaching'] if row['teacher_id']==scope['teacher_id']]
            classes=[row for row in classes if row['id'] in {load['class_id'] for load in loads}]
            subjects=[row for row in subjects if row['id'] in {load['subject_id'] for load in loads}]
        if report_code not in ('class_summary','teacher_analysis'):classes,subjects=await data_repo.teacher_references(db,user.school_id,year,scope['teacher_id'],integer(params.get('subject_id')))
    else:scope['teacher_name']=None
    bounds=report_algorithm_bounds(context.get('algorithm_parameters'),context['target_kind'],context['target_value'],catalog) if catalog else (context.get('algorithm_parameters') or {})
    scope_pairs=bounds.get('subject_class_pairs') if bounds.get('version')==2 else None
    permitted_subject_ids=sorted(set(bounds.get('subject_ids', []))) if bounds.get('version')==2 and (bounds.get('scope')!='class' or context['target_kind'] in ('subject','teacher','primary_teacher')) else []
    if bounds.get('version')==2:
        allowed_class_ids=set(bounds.get('class_ids', []))
        classes=[row for row in classes if row['id'] in allowed_class_ids]
        if permitted_subject_ids:
            subjects=[row for row in subjects if row['id'] in permitted_subject_ids]
    if scope['grades']:classes=[c for c in classes if c['grade_level'] in scope['grades']]
    if scope['class_id']:classes=[c for c in classes if c['id']==scope['class_id']]
    if scope['subject_id'] and integer(params.get('subject_id')) not in (None,scope['subject_id']):
        raise QualityReportError('Предмет не соответствует выбранному отчёту. / Пән таңдалған есепке сәйкес келмейді.')
    subject_id=scope['subject_id'] or integer(params.get('subject_id'))
    if not subject_id and len(permitted_subject_ids)==1:subject_id=permitted_subject_ids[0]
    if subject_id and subject_id not in {s['id'] for s in subjects}:
        raise QualityReportError('Предмет недоступен для выбранного объекта. / Пән таңдалған нысанға қолжетімсіз.')
    # Class inspection always covers all assessed subjects.
    if scope['mode']=='class':subject_id=None
    if scope['mode']=='area' and subject_id:
        matching_classes={p['class_id'] for p in (scope_pairs or []) if p['subject_id']==subject_id}
        classes=[c for c in classes if c['id'] in matching_classes]
    grade=integer(params.get('grade'))
    if not grade and bounds.get('version')==2 and len({row['grade_level'] for row in classes})==1:grade=classes[0]['grade_level']
    if grade and grade not in {c['grade_level'] for c in classes}:
        raise QualityReportError('Параллель недоступна. / Сынып деңгейі қолжетімсіз.')
    chosen_classes=ids(params,'class_ids')
    if not chosen_classes and scope['class_id']:chosen_classes=[scope['class_id']]
    if not chosen_classes and bounds.get('version')==2:chosen_classes=[row['id'] for row in classes if not grade or row['grade_level']==grade]
    permitted_classes={c['id'] for c in classes if not grade or c['grade_level']==grade}
    if params.get('refresh'):chosen_classes=[i for i in chosen_classes if i in permitted_classes]
    if not set(chosen_classes).issubset(permitted_classes):
        raise QualityReportError('Класс не входит в выбранную область. / Сынып таңдалған ауқымға кірмейді.')
    if scope['mode']=='subject' and grade and not chosen_classes:
        chosen_classes=[c['id'] for c in classes if c['grade_level']==grade]
    dates={}
    for key in ['date_from','date_to']:
        raw=params.get(key) or ''
        try:dates[key]=date.fromisoformat(str(raw)) if raw else None
        except ValueError:raise QualityReportError('Проверьте даты периода. / Кезең күндерін тексеріңіз.')
    if dates['date_from'] and dates['date_to'] and dates['date_from']>dates['date_to']:
        raise QualityReportError('Начало периода позже окончания. / Кезеңнің басы соңынан кейін.',field='inspection_date_to')
    checkpoint=str(params.get('checkpoint') or '')
    if checkpoint not in ('','baseline','quarter_1','quarter_2','quarter_3','quarter_4','final'):
        raise QualityReportError('Неизвестная контрольная точка. / Белгісіз бақылау нүктесі.')
    filters=dict(year=year,subject_id=subject_id,grade=grade,class_ids=chosen_classes,checkpoint=checkpoint,**dates)
    ready=(scope['mode']=='teacher' and (subject_id is not None or report_code=='teacher_analysis')) or (scope['mode']=='subject' and grade is not None) or (scope['mode'] in ('class','area') and bool(chosen_classes))
    if bounds.get('version')==2 and not chosen_classes:ready=False
    candidates=await data_repo.candidates(db,school_id=user.school_id,teacher_id=scope['teacher_id'],subject_ids=permitted_subject_ids,subject_class_pairs=scope_pairs,**filters) if ready and assessment_enabled() else []
    if len(candidates)>10000:raise QualityReportError('Слишком много вариантов. Уточните классы или период. / Нұсқалар тым көп. Сыныптарды немесе кезеңді нақтылаңыз.')
    choices=work_choices(candidates)
    overflow=len(choices)>200
    choices=choices[:200]
    permitted_groups={gid for work in choices for gid in work['group_ids']}
    candidates=[row for row in candidates if row['group_id'] in permitted_groups]
    quality_enabled=assessment_enabled() and (report_code not in ('class_summary','teacher_analysis') or params.get('inspection_form_version')!='1' or 'quality' in inspection_list(params,'inspection_sections'))
    selected,selection_expanded=resolve_work_selection(params,choices,quality_enabled=quality_enabled)
    selected_groups=set(selected)
    for work in choices:work['is_selected']=bool(selected_groups.intersection(work['group_ids']))
    page=dict(context=context,scope=scope,filters=filters,classes=classes,subjects=subjects,
        candidates=candidates,work_choices=choices,selected=selected,selection_expanded=selection_expanded,overflow=overflow,document=dict(doc) if doc else None,
        form_values={key:str(params[key]) for key in ('conclusion','recommendations','document_language') if key in params})
    if report_code in ('class_summary','teacher_analysis'):await prepare_inspection_page(db,user,page,params,catalog)
    return page


COUNT_KEYS=['total_students','participated_students','absent_students','excused_students','not_completed_students',
    'grade_2_count','grade_3_count','grade_4_count','grade_5_count']
SUM_KEYS=['score_sum','percent_sum']


def metrics(row):
    args={k:int(row[k] or 0) for k in COUNT_KEYS}
    args.update({k:Decimal(row[k] or 0) for k in SUM_KEYS})
    # The calculator's count invariant expects every pupil to belong to a bucket.
    missing=args['total_students']-sum(args[k] for k in ['participated_students','absent_students','excused_students','not_completed_students'])
    args['not_completed_students']+=missing
    return dict(row,**args,**asdict(KnowledgeQualityCalculator.calculate(**args)),missing_results=missing)


def build_snapshot(page,aggregates,objectives,*,language,conclusion='',recommendations=''):
    by_group={r['group_id']:r for r in aggregates}
    chosen=[r for r in page['candidates'] if r['group_id'] in page['selected']]
    if len(chosen)!=len(page['selected']) or (not chosen and page['context'].get('report_code') not in ('class_summary','teacher_analysis')):raise QualityReportError('Выберите завершённые работы. / Аяқталған жұмыстарды таңдаңыз.')
    if set(by_group)!={r['group_id'] for r in chosen}:raise QualityReportError('Результаты изменились. Обновите отчёт. / Нәтижелер өзгерді. Есепті жаңартыңыз.')
    rows=[]
    for item in chosen:
        row=metrics(by_group[item['group_id']]);rows.append(dict(item,**{k:v for k,v in row.items() if k!='group_id'}))
    # Totals only within the SAME assessment, parallel and track. Never merge different works/timepoints/subjects.
    totals=defaultdict(list)
    for row in rows:totals[(work_key(row),row['grade'],row['education_track'])].append(row)
    def combine(items):
        # Recalculate weighted metrics from counts/sums, never average rounded percentages.
        sums={k:sum(int(i[k] or 0) for i in items) for k in COUNT_KEYS}
        sums.update({k:sum(Decimal(i[k] or 0) for i in items) for k in SUM_KEYS})
        maximums=sorted({Decimal(str(i['max_score'])) for i in items if i.get('max_score') is not None})
        result=dict(items[0],**metrics(sums),assessment_ids=sorted({i['assessment_id'] for i in items}),
            group_ids=sorted({i['group_id'] for i in items}),class_names=sorted({i['class_name'] for i in items}),
            max_scores=maximums,max_score=maximums[0] if len(maximums)==1 else None)
        earned=[Decimal(str(i['highest_score'])) for i in items if i.get('highest_score') is not None]
        result['highest_score']=max(earned) if earned and len(maximums)==1 else None
        result['missing_results']=sum(int(i.get('missing_results') or 0) for i in items)
        if len(maximums)!=1 or any(i.get('max_score') is None for i in items):
            # Different scales cannot produce a meaningful common raw-score average.
            result['average_score']=None
        return result
    rank={'baseline':0,**{'quarter_'+str(i):i for i in range(1,5)},'final':5}
    combined=[combine(items) for items in totals.values()]
    combined.sort(key=lambda row:rank.get(value(row.get('checkpoint')),99))
    # Online variants are separate Assessments but one class measurement within a
    # diagnostic subject. Keep source rows intact for reopening/validating selections.
    by_class=defaultdict(list)
    for row in rows:
        by_class[(work_key(row),row['subject_id'],row['class_id'],row['grade'],row['education_track'])].append(row)
    class_rows=[combine(items) for items in by_class.values()]
    goals=[]
    row_by_group={row['group_id']:row for row in rows}
    by_objective=defaultdict(list)
    for obj in objectives:
        source_row=row_by_group[obj['group_id']]
        identity=('id',obj['learning_objective_id']) if obj.get('learning_objective_id') else ('code',obj['code'])
        key=(work_key(source_row),source_row['subject_id'],source_row['class_id'],source_row['education_track'],identity)
        by_objective[key].append((obj,source_row))
    for entries in by_objective.values():
        obj,source_row=entries[0]
        maximum=sum(Decimal(o['max_sum'] or 0) for o,_ in entries)
        score=sum(Decimal(o['score_sum'] or 0) for o,_ in entries)
        title=obj['title'] or ''
        # Legacy objective snapshots can contain $...$ or $$...$$. Feed these
        # into the existing shared formatter; do not create a second math parser.
        title=re.sub(r'\$\$(.*?)\$\$|(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)',
            lambda match:r'\('+ (match.group(1) if match.group(1) is not None else match.group(2)) +r'\)',title,flags=re.DOTALL)
        checkpoint=value(source_row.get('checkpoint'))
        roman={'quarter_1':'I','quarter_2':'II','quarter_3':'III','quarter_4':'IV'}.get(checkpoint)
        if roman:work_labels={'ru':roman+' четверть','kk':roman+' тоқсан'}
        elif checkpoint=='baseline':work_labels={'ru':'Нулевой контроль','kk':'Нөлдік бақылау'}
        elif checkpoint=='final':work_labels={'ru':'Итоговая работа','kk':'Жылдық қорытынды'}
        else:work_labels={'ru':'Без четверти','kk':'Тоқсансыз'}
        goals.append(dict(obj,checkpoint=checkpoint,work_labels=work_labels,class_name=source_row['class_name'],assessment_id=source_row['assessment_id'],titles=source_row.get('titles') or {},
            assessment_ids=sorted({row['assessment_id'] for _,row in entries}),group_ids=sorted({o['group_id'] for o,_ in entries}),
            students=sum(int(o['students'] or 0) for o,_ in entries),score_sum=score,max_sum=maximum,
            title_blocks=explanation_blocks(title,language=language),
            percent=(score*100/maximum).quantize(Decimal('.01'),ROUND_HALF_UP) if maximum else None))
    goals.sort(key=lambda g:(tuple(int(n) for n in re.findall(r'\d+',g['code'])),g['group_id']))
    # Combine online variants of the same diagnostic subject before comparing checkpoints.
    measurements=defaultdict(list)
    for row in rows:
        if row['checkpoint']:measurements[(row['subject_id'],row['class_id'],row['education_track'],work_key(row))].append(row)
    timeline=defaultdict(list)
    for key,items in measurements.items():
        timeline[key[:3]].append(combine(items))
    dynamics=[]
    for items in timeline.values():
        points=defaultdict(list)
        for item in items:points[value(item['checkpoint'])].append(item)
        # Several independent works at the same checkpoint are not silently averaged or selected.
        ordered=[v[0] for k,v in sorted(points.items(),key=lambda p:rank.get(p[0],99)) if len(v)==1]
        for before,after in zip(ordered,ordered[1:]):
            dynamics.append(dict(subject_titles={'ru':after['name_ru'],'kk':after['name_kz']},subject=after['name_ru'] if language=='ru' else after['name_kz'],class_name=after['class_name'],
                before=before['title'],after=after['title'],before_titles=before.get('titles') or {},after_titles=after.get('titles') or {},before_n=before['participated_students'],after_n=after['participated_students'],
                before_max_scores=before['max_scores'],after_max_scores=after['max_scores'],
                before_highest_score=before['highest_score'],after_highest_score=after['highest_score'],
                before_quality=before['quality_percent'],after_quality=after['quality_percent'],
                delta=(after['quality_percent']-before['quality_percent']) if before['quality_percent'] is not None and after['quality_percent'] is not None else None))
    code=page['context'].get('report_code','knowledge_quality_table')
    return json_value(dict(kind='vsk_assessment_summary' if code in ('class_summary','teacher_analysis') else 'vsk_assessment_quality',report_code=code,schema_version=1,report_layout_version=160,language=language,created_at=datetime.now(timezone.utc),
        school_name=page['context']['school_name'],target_label=page['context']['target_label'],target_labels=page['context'].get('target_labels') or {},mode=page['scope']['mode'],
        teacher_name=page['scope']['teacher_name'],filters=page['filters'],rows=rows,class_rows=class_rows,totals=combined,objectives=goals,dynamics=dynamics,
        analysis_objectives=sorted(goals,key=lambda g:(g['percent'] is None,g['percent'] or Decimal(0),g['code'],g['group_id']))[:20],
        conclusion=conclusion.strip(),recommendations=recommendations.strip()))


async def calculate(db,user,page,params,language):
    ensure_report(page['context']['report_code'])
    if not assessment_enabled() and 'quality' in inspection_list(params,'inspection_sections'):raise FeatureUnavailable()
    if REPORT_TYPES[page['context']['report_code']].get('structured'):
        from app.modules.reports.services import structured_report_service
        return await structured_report_service.calculate(db,user,page,params,language)
    inspection=build_inspection(page,params) if page['context'].get('report_code') in ('class_summary','teacher_analysis') else None
    calculation_page=page
    if inspection and 'quality' not in inspection['sections']:calculation_page=dict(page,selected=[])
    kwargs=dict(school_id=user.school_id,year=page['filters']['year'],group_ids=calculation_page['selected'],teacher_id=page['scope']['teacher_id'])
    if not calculation_page['selected'] and inspection is None:raise QualityReportError('Выберите работы. / Жұмыстарды таңдаңыз.')
    data=await data_repo.aggregates(db,**kwargs) if calculation_page['selected'] else []
    goals=await data_repo.objectives(db,**kwargs) if calculation_page['selected'] else []
    snapshot=build_snapshot(calculation_page,data,goals,language=language,
        conclusion=str(params.get('conclusion') or '')[:10000],recommendations=str(params.get('recommendations') or '')[:10000])
    if inspection:snapshot['inspection']=inspection
    snapshot['report_titles']={lang:REPORT_TYPES[page['context']['report_code']]['title_'+lang] for lang in ('ru','kk')}
    return snapshot


def checked_document(presence,compliance,note,*,completing=False,prefix=''):
    """The same presence/compliance semantics as the teacher inspection."""
    if presence not in ('not_checked','yes','no'):raise QualityReportError('Укажите наличие документа. / Құжаттың бар-жоғын көрсетіңіз.',field=prefix+'presence')
    if presence!='yes':compliance='not_applicable' if presence=='no' else 'not_checked'
    if compliance not in ('not_checked','complies','non_compliant','not_applicable') or (presence=='yes' and compliance=='not_applicable'):
        raise QualityReportError('Выберите соответствие требованиям. / Талаптарға сәйкестігін таңдаңыз.',field=prefix+'compliance')
    if compliance=='non_compliant' and not note:raise QualityReportError('При несоответствии укажите замечание. / Сәйкес келмесе, ескертпе жазыңыз.',field=prefix+'note')
    if completing and (presence=='not_checked' or (presence=='yes' and compliance=='not_checked')):
        raise QualityReportError('Завершите проверку наличия и соответствия документа. / Құжаттың бар-жоғы мен сәйкестігін тексеруді аяқтаңыз.',field=prefix+('presence' if presence=='not_checked' else 'compliance'))
    return dict(presence=presence,compliance=compliance,note=note)


def is_snapshot(data,report_code):
    return data.get('kind') in ('vsk_assessment_quality','vsk_assessment_summary','vsk_structured_report') and data.get('report_code','knowledge_quality_table')==report_code

# One set of parameters for the existing class_summary document, not new report models.
INSPECTION_SECTIONS={
 'ktp':{'ru':'КТП','kk':'КТЖ'},'ksp':{'ru':'КСП','kk':'ҚМЖ'},
 'gifted':{'ru':'План работы с одарёнными детьми','kk':'Дарынды балалармен жұмыс жоспары'},
 'struggling':{'ru':'План работы с неуспевающими детьми','kk':'Үлгерімі төмен оқушылармен жұмыс жоспары'},
 'self_education':{'ru':'План самообразования','kk':'Өз білімін жетілдіру жоспары'},
 'mentor_plan':{'ru':'План работы с наставником','kk':'Тәлімгермен жұмыс жоспары'},
 'homeroom_documents':{'ru':'Документы классного руководителя','kk':'Сынып жетекшісінің құжаттары'},
 'visits':{'ru':'Взаимопосещения уроков за период','kk':'Кезеңдегі өзара сабаққа қатысу'},
 'quality':{'ru':'Качество знаний','kk':'Білім сапасы'},
 'lessons':{'ru':'Наблюдение урока','kk':'Сабақты бақылау'},
 'notebooks':{'ru':'Проверка тетрадей','kk':'Дәптерлерді тексеру'},
 'reading':{'ru':'Чтение, 1–4 классы','kk':'Оқу, 1–4 сыныптар'}}
INSPECTION_DOCUMENTS=('ktp','ksp','gifted','struggling','self_education','homeroom_documents','mentor_plan')
INSPECTION_VISIT_PURPOSES={
 'experience_exchange':{'ru':'Обмен опытом','kk':'Тәжірибе алмасу'},
 'open_lesson':{'ru':'Открытый урок','kk':'Ашық сабақ'},
 'mentoring':{'ru':'Наставничество','kk':'Тәлімгерлік'}}
INSPECTION_VISIT_CONFIRMATIONS={
 'journal':{'ru':'Журнал взаимопосещений','kk':'Өзара сабаққа қатысу журналы'},
 'dates':{'ru':'Даты посещений','kk':'Қатысу күндері'},
 'sheets':{'ru':'Листы посещения','kk':'Сабаққа қатысу парақтары'}}
ADAL_AZAMAT_CRITERIA={key:dict(ru=ru,kk=kk) for key,ru,kk in [
 ('class_year','Указаны класс и учебный год','Сынып пен оқу жылы көрсетілген'),
 ('patriotism','Независимость и патриотизм','Тәуелсіздік және отаншылдық'),
 ('unity','Единство и солидарность','Бірлік және ынтымақ'),
 ('responsibility','Справедливость и ответственность','Әділдік және жауапкершілік'),
 ('law','Закон и порядок','Заң және тәртіп'),
 ('work','Трудолюбие и профессионализм','Еңбекқорлық және кәсіби біліктілік'),
 ('creativity','Созидание и новаторство','Жасампаздық және жаңашылдық'),
 ('class_hours','Планирование классных часов','Сынып сағаттарын жоспарлау'),
 ('safety','Безопасность и профилактика','Қауіпсіздік және алдын алу'),
 ('projects','Участие класса в социальных проектах','Сыныптың әлеуметтік жобаларға қатысуы'),
 ('parents','Работа с родителями','Ата-аналармен жұмыс'),
 ('organization','Сроки, ответственные и подведение итогов','Мерзімдер, жауаптылар және қорытындылау')]}
ADAL_AZAMAT_META=dict(code='adal_azamat',criteria_version=1,source_year=2025,
 source_url='https://uba.edu.kz/storage/app/media/99999%20VVV%20MMM%20RS%20RS.pdf',
 title={'ru':'План воспитательной работы по программе «Адал азамат»','kk':'«Адал азамат» бағдарламасы бойынша тәрбие жұмысының жоспары'})


INSPECTION_STATES={key:dict(ru=ru,kk=kk) for key,ru,kk in [
 ('not_checked','Не проверено','Тексерілмеген'),('yes','Есть','Бар'),('no','Нет','Жоқ'),
 ('complies','Соответствует','Сәйкес келеді'),('non_compliant','Не соответствует','Сәйкес келмейді'),
 ('not_applicable','Не применяется','Қолданылмайды'),('pending','Ожидается отчёт','Есеп күтілуде'),
 ('completed','Завершён','Аяқталған'),('waived','Освобождён','Босатылған'),
 ('outside_period','Вне периода проверки','Тексеру кезеңінен тыс'),('outside_scope','Другой класс','Басқа сынып')]}


def inspection_list(params,key):
    values=params.getlist(key) if hasattr(params,'getlist') else params.get(key,[])
    return [str(v) for v in (values if isinstance(values,(list,tuple)) else [values]) if str(v)]


async def prepare_inspection_page(db,user,page,params,catalog):
    """Use the existing school's workload catalog, bounded by the algorithm/report scope."""
    classes={row['id']:row for row in page['classes'] if not page['filters']['grade'] or row['grade_level']==page['filters']['grade']}
    if page['filters']['class_ids']:classes={cid:row for cid,row in classes.items() if cid in page['filters']['class_ids']}
    subject_ids={row['id'] for row in page['subjects']}
    if page['filters']['subject_id']:subject_ids={page['filters']['subject_id']}
    bounds=page['context'].get('algorithm_parameters') or {}
    effective=report_algorithm_bounds(bounds,page['context']['target_kind'],page['context']['target_value'],catalog)
    allowed_pairs={(p['subject_id'],p['class_id']) for p in effective.get('subject_class_pairs',[])} if effective.get('version')==2 else None
    requested=set(bounds.get('teacher_ids') or [])
    default_teachers=set(requested)
    for values in (bounds.get('report_teacher_ids') or {}).values():default_teachers.update(values)
    pool={}
    subjects={row['id']:row for row in catalog['subjects']}
    for assignment in catalog['teaching']:
        tid=assignment['teacher_id'];cid=assignment['class_id'];sid=assignment['subject_id']
        if allowed_pairs is not None and (sid,cid) not in allowed_pairs:continue
        if cid not in classes or sid not in subject_ids or (page['scope']['teacher_id'] and tid!=page['scope']['teacher_id']):continue
        if requested and tid not in requested:continue
        teacher=pool.setdefault(tid,dict(id=tid,name=assignment['full_name'],classes={},subjects={}))
        teacher['classes'].setdefault(cid, dict(classes[cid], subject_ids=set()))['subject_ids'].add(sid)
        teacher['subjects'][sid]=subjects[sid]
    if len(pool)>100:raise QualityReportError('Уточните предметы и классы: не более 100 учителей в одном отчёте. / Пәндер мен сыныптарды нақтылаңыз: бір есепте 100 мұғалімнен аспайды.')
    teachers=[dict(t,class_names=', '.join(c['name'] for c in t['classes'].values()),
        grades=sorted({c['grade_level'] for c in t['classes'].values()}),
        subject_names={lang:', '.join((s.get('name_ru') or s.get('name_kz') or '') if lang=='ru' else (s.get('name_kz') or s.get('name_ru') or '') for s in t['subjects'].values()) for lang in ('ru','kk')}) for t in sorted(pool.values(),key=lambda t:(t['name'],t['id']))]
    saved=((page['document'] or {}).get('schema_json') or {}).get('inspection') or {}
    form={};posted=params.get('inspection_form_version')=='1'
    if posted:
        form={str(k):str(v) for k,v in params.items() if str(k).startswith('inspection_')}
        selected=inspection_list(params,'inspection_teacher_ids');sections=inspection_list(params,'inspection_sections')
        for teacher in teachers:
            for field in ('purposes','confirmations'):
                key='inspection_'+str(teacher['id'])+'_visits_'+field;form[key]=inspection_list(params,key)
    elif saved:
        selected=[str(t['id']) for t in saved['teachers']];sections=saved['sections']
        form.update(inspection_date_from=saved['date_from'],inspection_date_to=saved['date_to'])
        for teacher in saved['teachers']:
            prefix='inspection_'+str(teacher['id'])+'_'
            plan=teacher.get('adal_azamat') or {}
            if plan:
                form[prefix+'adal_class_id']=str(plan.get('class_id') or '')
                for item in plan.get('criteria',[]):
                    form[prefix+'adal_'+item['code']+'_state']=item['state'];form[prefix+'adal_'+item['code']+'_note']=item['note']
                execution=plan.get('execution') or {}
                form[prefix+'adal_check_execution']='1' if execution.get('enabled') else ''
                form[prefix+'adal_execution_state']=execution.get('state','not_checked');form[prefix+'adal_execution_note']=execution.get('note','')
            for item in teacher['documents']:
                for field in ('presence','compliance','note'):form[prefix+item['code']+'_'+field]=('not_checked' if item['code']=='homeroom_documents' and field=='presence' and item[field]=='not_applicable' else item[field])
            for field in ('count','proof'):form[prefix+'visits_'+field]='' if teacher['visits'][field] is None else str(teacher['visits'][field])
            for field in ('purposes','confirmations'):form[prefix+'visits_'+field]=teacher['visits'].get(field,[])
            for field in ('checked','below','criteria','note','source_document_id'):form[prefix+'reading_'+field]='' if teacher['reading'].get(field) is None else str(teacher['reading'].get(field))
    else:
        selected=[str(t['id']) for t in teachers if not default_teachers or t['id'] in default_teachers];sections=['ktp','ksp','gifted','struggling','self_education','visits']
        for report,section in [('lesson_observation','lessons'),('checking_notebooks_table','notebooks'),('reading_speed_table','reading')]:
            if report in bounds.get('report_types',[]):sections.append(section)
        if page['selected']:sections.append('quality')
    import calendar
    month=page['context'].get('month') or 9;year=page['filters']['year']+(month<8)
    form.setdefault('inspection_date_from',date(year,month,1).isoformat())
    form.setdefault('inspection_date_to',date(year,month,calendar.monthrange(year,month)[1]).isoformat())
    for teacher in teachers:
        if len(teacher['classes'])==1:form.setdefault('inspection_'+str(teacher['id'])+'_adal_class_id',str(next(iter(teacher['classes']))))
    if not assessment_enabled():sections=[code for code in sections if code!='quality']
    page.update(adal_criteria=ADAL_AZAMAT_CRITERIA,adal_meta=ADAL_AZAMAT_META,inspection_visit_confirmations=INSPECTION_VISIT_CONFIRMATIONS,inspection_teachers=teachers,inspection_form=form,inspection_selected=selected,inspection_sections=sections)
    page['inspection_sources']=(await report_repo.inspection_sources(db,school_id=user.school_id,task_id=page['context']['task_id'],
        teacher_ids=[integer(tid) for tid in selected],sections=sections)) if set(sections).intersection({'lessons','notebooks','reading'}) else []
    if len(page['inspection_sources'])>2000:raise QualityReportError('В задаче слишком много исходных отчётов. Уточните область контроля. / Тапсырмада бастапқы есептер тым көп. Бақылау ауқымын нақтылаңыз.')
    reading_sources=[r for r in page['inspection_sources'] if r['code']=='reading_speed_table' and isinstance(r.get('reading_summary'),dict)
        and value(r['document_status']) in ('submitted','approved','accepted') and value(r['assignment_status'])!='waived']
    for teacher in teachers:
        teacher['reading_sources']=[r for r in reading_sources if r['reading_summary'].get('class_ids') and set(r['reading_summary']['class_ids']).issubset(teacher['classes'])
            and form['inspection_date_from']<=r['reading_summary'].get('check_date','')<=form['inspection_date_to']]
        if len(teacher['reading_sources'])>100:raise QualityReportError('Уточните период чтения: более 100 исходных отчётов для одного учителя. / Оқу кезеңін нақтылаңыз: бір мұғалімге 100 бастапқы есептен артық.')



def build_inspection(page,params):
    """Validate manual fields once and freeze existing source metrics without re-entering them."""
    form=page['inspection_form'];selected=page['inspection_selected'];sections=list(dict.fromkeys(page['inspection_sections']))
    if not sections or not set(sections).issubset(set(INSPECTION_SECTIONS)-{'mentor_plan'}):raise QualityReportError('Выберите направления проверки. / Тексеру бағыттарын таңдаңыз.',field='inspection_sections')
    pool={str(t['id']):t for t in page['inspection_teachers']}
    if len(selected)>100 or not set(selected).issubset(pool):raise QualityReportError('Учитель не входит в область проверки. Обновите параметры. / Мұғалім тексеру ауқымына кірмейді. Параметрлерді жаңартыңыз.')
    if set(sections)-{'quality'} and not selected:raise QualityReportError('Выберите проверяемых учителей. / Тексерілетін мұғалімдерді таңдаңыз.',field='inspection_teacher_ids')
    try:start=date.fromisoformat(form['inspection_date_from']);end=date.fromisoformat(form['inspection_date_to'])
    except (ValueError,KeyError):raise QualityReportError('Укажите период проверки. / Тексеру кезеңін көрсетіңіз.',field='inspection_date_from')
    if start>end:raise QualityReportError('Начало периода позже окончания. / Кезеңнің басы соңынан кейін.',field='inspection_date_to')
    completing=params.get('action')=='complete'
    def text(key):
        raw=form.get(key,'').strip()
        if len(raw)>2000:raise field_error('Не более 2000 символов. / 2000 таңбадан аспайды.',key)
        return raw
    def count(key):
        raw=form.get(key,'').strip()
        if not raw:return None
        if not re.fullmatch(r'[0-9]{1,5}',raw) or int(raw)>10000:raise field_error('Введите целое число от 0 до 10000. / 0–10000 аралығындағы бүтін санды енгізіңіз.',key)
        return int(raw)
    def field_error(message,key):
        tail=key.removeprefix(prefix)
        section=next((code for code in (*INSPECTION_DOCUMENTS,'visits','reading') if tail.startswith(code+'_')),None)
        field=tail[len(section)+1:] if section else tail
        names={'count':('Количество уроков','Сабақ саны'),'purposes':('Цель посещения','Қатысу мақсаты'),'confirmations':('Подтверждение','Растау'),'proof':('Уточнение','Нақтылау'),'checked':('Проверено учеников','Тексерілген оқушылар'),'below':('Ниже критерия','Критерийден төмен'),'criteria':('Критерий и основание','Критерий және негіздеме'),'note':('Замечание','Ескертпе')}
        a,b=names.get(field,('Поле проверки','Тексеру өрісі'))
        return review_error(message,teacher=reference,section=section,parameter=dict(ru=a,kk=b),field=key)
    teachers=[]
    for tid in dict.fromkeys(selected):
        reference=pool[tid];prefix='inspection_'+tid+'_';homeroom='homeroom_documents' in sections;documents=[]
        purposes=list(dict.fromkeys(inspection_list(form,prefix+'visits_purposes'))) if 'visits' in sections else []
        if not set(purposes).issubset(INSPECTION_VISIT_PURPOSES):raise field_error('Выберите цель посещения из списка. / Қатысу мақсатын тізімнен таңдаңыз.',prefix+'visits_purposes')
        confirmations=list(dict.fromkeys(inspection_list(form,prefix+'visits_confirmations'))) if 'visits' in sections else []
        if not set(confirmations).issubset(INSPECTION_VISIT_CONFIRMATIONS):raise field_error('Выберите подтверждение посещения из списка. / Қатысуды растау түрін тізімнен таңдаңыз.',prefix+'visits_confirmations')
        mentoring='mentoring' in purposes
        for code in INSPECTION_DOCUMENTS:
            if code=='homeroom_documents':continue
            if code=='mentor_plan':
                if not mentoring:continue
            elif code not in sections:continue
            presence=form.get(prefix+code+'_presence') or 'not_checked';compliance=form.get(prefix+code+'_compliance') or 'not_checked';note=text(prefix+code+'_note')
            try:
                check=checked_document(presence,compliance,note,completing=completing,prefix=prefix+code+'_')
            except QualityReportError as exc:
                suffix=(exc.field or '').removeprefix(prefix+code+'_')
                labels={'presence':dict(ru='Наличие документа',kk='Құжаттың бар-жоғы'),'compliance':dict(ru='Соответствие требованиям',kk='Талаптарға сәйкестігі'),'note':dict(ru='Замечание',kk='Ескертпе')}
                raise review_error(exc.messages,teacher=reference,section=code,parameter=labels.get(suffix),field=exc.field) from exc
            presence=check['presence'];compliance=check['compliance']
            documents.append(dict(code=code,presence=presence,compliance=compliance,note=note))
        plan=build_adal_azamat(form,prefix,reference,page['filters']['year'],completing) if homeroom else None
        if plan:documents.append(dict(code='homeroom_documents',presence=plan['presence'],compliance=plan['compliance'],note=plan['note']))
        visits=dict(count=count(prefix+'visits_count') if 'visits' in sections else None,proof=text(prefix+'visits_proof') if 'visits' in sections else '',purposes=purposes,confirmations=confirmations)
        if 'visits' in sections and completing and visits['count'] is None:raise field_error('Укажите количество взаимопосещений, включая 0. / Өзара сабаққа қатысу санын, соның ішінде 0 санын көрсетіңіз.',prefix+'visits_count')
        if visits['count'] and not purposes:raise field_error('Укажите цель взаимопосещения уроков. / Өзара сабаққа қатысу мақсатын көрсетіңіз.',prefix+'visits_purposes')
        if visits['count'] and not confirmations and not visits['proof']:raise field_error('Отметьте подтверждение взаимопосещений. / Өзара сабаққа қатысуды растау түрін белгілеңіз.',prefix+'visits_confirmations')
        reading=dict(checked=None,below=None,criteria='',note='')
        if 'reading' in sections:
            if any(grade>4 or grade<1 for grade in reference['grades']):raise field_error('Для чтения выберите только 1–4 классы. / Оқу үшін тек 1–4 сыныптарды таңдаңыз.',prefix+'reading_checked')
            source_id=integer(form.get(prefix+'reading_source_document_id'))
            if source_id:
                source=next((r for r in page['inspection_sources'] if r['code']=='reading_speed_table' and r['document_id']==source_id),None)
                summary=(source or {}).get('reading_summary') or {}
                if not isinstance(summary,dict):summary={}
                if (not source or value(source['document_status']) not in ('submitted','approved','accepted') or value(source['assignment_status'])=='waived'
                        or not set(summary.get('class_ids') or []).issubset(reference['classes']) or not summary.get('class_ids')):
                    raise field_error('Выберите завершённый отчёт чтения по классам учителя. / Мұғалімнің сыныптары бойынша аяқталған оқу есебін таңдаңыз.',prefix+'reading_source_document_id')
                try:observed=date.fromisoformat(summary.get('check_date',''))
                except ValueError:raise field_error('В исходном отчёте нет даты чтения. / Бастапқы есепте оқу күні жоқ.',prefix+'reading_source_document_id')
                if not start<=observed<=end:raise field_error('Отчёт чтения вне периода проверки. / Оқу есебі тексеру кезеңінен тыс.',prefix+'reading_source_document_id')
                reading=dict(checked=summary.get('checked'),below=summary.get('below'),criteria=summary.get('criteria',''),note=text(prefix+'reading_note'),source_document_id=source_id,
                    class_names=summary.get('class_names',[]),average_wpm=summary.get('average_wpm'),threshold=summary.get('threshold'))
            else:
                reading=dict(checked=count(prefix+'reading_checked'),below=count(prefix+'reading_below'),criteria=text(prefix+'reading_criteria'),note=text(prefix+'reading_note'),source_document_id=None)
            if reading['below'] is not None and (reading['checked'] is None or reading['below']>reading['checked']):raise field_error('Количество ниже критерия не может превышать число проверенных. / Критерийден төмен саны тексерілгендер санынан аспауы тиіс.',prefix+'reading_below')
            if (reading['checked'] is not None and not reading['criteria']) or (completing and (reading['checked'] is None or reading['below'] is None)):raise field_error('Заполните показатель или критерий чтения. / Оқу көрсеткішін немесе критерийін толтырыңыз.',prefix+('reading_checked' if reading['checked'] is None else 'reading_below' if reading['below'] is None else 'reading_criteria'))
        teachers.append(dict(id=reference['id'],name=reference['name'],class_names=reference['class_names'],subject_names=reference['subject_names'],homeroom=homeroom,adal_azamat=plan,documents=documents,visits=visits,reading=reading))
    sources=[];selected_ids={str(t['id']) for t in teachers}
    index=class_index({c['id']:c for c in page['classes']})
    for source in page['inspection_sources']:
        section={'lesson_observation':'lessons','checking_notebooks_table':'notebooks','reading_speed_table':'reading'}[source['code']]
        if section not in sections:continue
        if section=='reading' and source['target_kind']=='class' and str(source['target_value']) not in {str(c['id']) for c in page['classes'] if not page['filters']['class_ids'] or c['id'] in page['filters']['class_ids']}:continue
        if section=='reading' and source['target_kind'] in ('parallel','parallel_class') and str(source['target_value']) not in {str(c['grade_level']) for c in page['classes'] if not page['filters']['class_ids'] or c['id'] in page['filters']['class_ids']}:continue
        if section in ('lessons','notebooks') and (source['target_kind'] not in ('teacher','primary_teacher') or str(source['target_value']) not in selected_ids):continue
        state='waived' if value(source['assignment_status'])=='waived' else 'completed' if value(source['document_status']) in ('submitted','approved','accepted') else 'pending'
        observed=source['lesson_date'] if section=='lessons' else source['notebook_date'] if section=='notebooks' else None
        class_name=source['lesson_class'] if section=='lessons' else source['notebook_class'] if section=='notebooks' else source['target_label']
        observed_day=(observed.astimezone(timezone(timedelta(hours=5))).date() if observed.tzinfo else observed.date()) if observed else None
        if state=='completed' and observed_day and not start<=observed_day<=end:state='outside_period'
        if completing and section in ('lessons','notebooks') and state=='pending':raise review_error('Завершите выбранные исходные отчёты перед завершением сводного. / Жинақ есепті аяқтамас бұрын таңдалған бастапқы есептерді аяқтаңыз.',teacher=source['target_label'],section=section,parameter=dict(ru='Исходный отчёт №'+str(source['document_id'] or source['selected_id']),kk='Бастапқы есеп №'+str(source['document_id'] or source['selected_id'])))
        if section in ('lessons','notebooks'):
            reference=pool[str(source['target_value'])]
            try: entries=source_rows(source,section,reference['classes'],index)
            except ValueError as exc: raise QualityReportError(str(exc)) from exc
        else:
            entries=[dict(class_name=class_name,class_id=None,subject_id=None,in_scope=True,score=None,max_score=None,note=source.get('notebook_conclusion') or '')]
        for entry in entries:
            entry_state='outside_scope' if state=='completed' and not entry['in_scope'] else state
            sources.append(dict(teacher_id=str(source['target_value']),code=source['code'],section=section,selected_id=source['selected_id'],document_id=source['document_id'],teacher=source['target_label'],class_name=entry['class_name'],
                class_id=entry['class_id'],subject_id=entry['subject_id'],grade_level=entry.get('grade_level'),state=entry_state,
                score=entry['score'] if entry_state=='completed' else None,
                max_score=entry['max_score'] if entry_state=='completed' else None,note=entry['note']))
            if len(sources)>5000:raise QualityReportError('Уточните область: более 5000 строк исходных отчётов. / Ауқымды нақтылаңыз: бастапқы есептерде 5000 жолдан артық.')
    covered={(row['section'],row['teacher_id']) for row in sources}
    for section,code in [('lessons','lesson_observation'),('notebooks','checking_notebooks_table')]:
        if section not in sections:continue
        for teacher in teachers:
            if (section,str(teacher['id'])) not in covered:
                if completing:raise review_error('В алгоритме выберите и завершите исходный отчёт. / Алгоритмде бастапқы есепті таңдап, аяқтаңыз.',teacher=teacher,section=section)
                sources.append(dict(teacher_id=str(teacher['id']),code=code,section=section,selected_id=None,document_id=None,teacher=teacher['name'],class_name=teacher['class_names'],state='not_checked',score=None,max_score=None,note=''))
    if 'quality' in sections and not page['selected']:raise review_error('Выберите оценочные работы. / Бағалау жұмыстарын таңдаңыз.',section='quality',field='work_ids' if page['candidates'] else 'grade')
    return json_value(dict(version=4,sections=sections,labels=INSPECTION_SECTIONS,visit_purposes=INSPECTION_VISIT_PURPOSES,visit_confirmations=INSPECTION_VISIT_CONFIRMATIONS,states=INSPECTION_STATES,date_from=start,date_to=end,teachers=teachers,sources=sources,source_groups=group_source_rows(sources)))


def work_key(row):
    return ('diagnostic',row['diagnostic_subject_id']) if row.get('diagnostic_subject_id') else ('assessment',row['assessment_id'])


def work_choice_key(row):
    kind,identifier=work_key(row)
    return ':'.join((kind,str(identifier),str(row['subject_id']),str(row['class_id'])))


def work_choices(rows):
    grouped={}
    for row in rows:grouped.setdefault(work_choice_key(row),[]).append(row)
    return [dict(items[0],key=key,group_ids=sorted({i['group_id'] for i in items}),
        assessment_ids=sorted({i['assessment_id'] for i in items}),students=sum(int(i['students']) for i in items),
        variants=len({i['assessment_id'] for i in items}),variant_rows=items) for key,items in grouped.items()]


def resolve_work_selection(params,choices,*,quality_enabled=True):
    if not quality_enabled:return [],False
    allowed={work['key']:work for work in choices}
    if params.get('work_selection_version')=='1':
        keys=set(inspection_list(params,'work_ids'))
        if len(keys)>200:raise QualityReportError('Выберите не более 200 работ. / 200 жұмыстан артық таңдамаңыз.')
        if params.get('refresh'):keys.intersection_update(allowed)
        if not keys.issubset(allowed):raise QualityReportError('Работа недоступна в выбранной области. Обновите список. / Жұмыс таңдалған ауқымға қолжетімсіз. Тізімді жаңартыңыз.')
        return sorted({gid for key in keys for gid in allowed[key]['group_ids']}),False
    # Existing drafts contain group IDs. Selecting any variant now selects the whole work.
    old=set(ids(params,'group_ids',limit=10000))
    permitted={gid for work in choices for gid in work['group_ids']}
    if params.get('refresh'):old.intersection_update(permitted)
    if not old.issubset(permitted):raise QualityReportError('Выбор работ не соответствует фильтру. Обновите список. / Жұмыстар сүзгіге сәйкес емес. Тізімді жаңартыңыз.')
    selected={gid for work in choices if old.intersection(work['group_ids']) for gid in work['group_ids']}
    return sorted(selected),bool(selected-old)


def build_adal_azamat(form,prefix,teacher,year,completing):
    """Review checklist in the existing snapshot; no automatic document/role verification."""
    def fail(message,key,parameter=None):
        return review_error(message,teacher=teacher,section=ADAL_AZAMAT_META['title'],parameter=parameter,field=prefix+key)
    def note(key):
        raw=str(form.get(prefix+key) or '').strip()
        if len(raw)>2000:raise fail('Замечание: не более 2000 символов. / Ескертпе: 2000 таңбадан аспайды.',key,ADAL_AZAMAT_CRITERIA.get(key[5:-5],dict(ru='Замечание',kk='Ескертпе')))
        return raw
    if str(form.get(prefix+'adal_version') or '1')!='1':raise fail('Версия критериев изменилась. Обновите форму. / Критерийлер нұсқасы өзгерді. Пішінді жаңартыңыз.','adal_version')
    presence=form.get(prefix+'homeroom_documents_presence') or 'not_checked'
    if presence not in ('not_checked','yes','no'):raise fail('Укажите наличие плана воспитательной работы. / Тәрбие жұмысы жоспарының бар-жоғын көрсетіңіз.','homeroom_documents_presence',dict(ru='Наличие плана',kk='Жоспардың бар-жоғы'))
    try:class_id=integer(form.get(prefix+'adal_class_id'))
    except QualityReportError:raise fail('Выберите класс плана. / Жоспар сыныбын таңдаңыз.','adal_class_id') from None
    if class_id is not None and class_id not in teacher['classes']:raise fail('Класс плана не входит в область проверки учителя. / Жоспар сыныбы мұғалімді тексеру ауқымына кірмейді.','adal_class_id',dict(ru='Класс плана',kk='Жоспар сыныбы'))
    if completing and class_id is None:raise fail('Выберите класс плана. / Жоспар сыныбын таңдаңыз.','adal_class_id',dict(ru='Класс плана',kk='Жоспар сыныбы'))
    if completing and presence=='not_checked':raise fail('Укажите наличие плана. / Жоспардың бар-жоғын көрсетіңіз.','homeroom_documents_presence',dict(ru='Наличие плана',kk='Жоспардың бар-жоғы'))
    allowed={'not_checked','complies','non_compliant','not_applicable'}
    def review(state_key,note_key):
        parameter=ADAL_AZAMAT_CRITERIA.get(state_key[5:-6],dict(ru='Выполнение за период',kk='Кезеңдегі орындалуы'))
        state=form.get(prefix+state_key) or 'not_checked';remark=note(note_key)
        if presence!='yes':return ('not_applicable' if presence=='no' else 'not_checked'),remark
        if state not in allowed:raise fail('Некорректная оценка критерия «Адал азамат». / «Адал азамат» критерийінің бағасы дұрыс емес.',state_key,parameter)
        if state=='non_compliant' and not remark:raise fail('При несоответствии критерия «Адал азамат» укажите замечание. / «Адал азамат» критерийі сәйкес келмесе, ескертпе жазыңыз.',note_key,parameter)
        if completing and state=='not_checked':raise fail('Завершите проверку критериев плана «Адал азамат». / «Адал азамат» жоспарының критерийлерін тексеруді аяқтаңыз.',state_key,parameter)
        return state,remark
    criteria=[]
    for code,title in ADAL_AZAMAT_CRITERIA.items():
        state,remark=review('adal_'+code+'_state','adal_'+code+'_note')
        if presence=='yes' and code=='class_year' and state=='not_applicable':raise fail('Для имеющегося плана проверьте класс и учебный год. / Бар жоспардың сыныбы мен оқу жылын тексеріңіз.','adal_class_year_state',ADAL_AZAMAT_CRITERIA['class_year'])
        criteria.append(dict(code=code,title=title,state=state,note=remark))
    states={item['state'] for item in criteria}
    compliance=('not_applicable' if presence=='no' else 'not_checked' if presence!='yes' else
        'non_compliant' if 'non_compliant' in states else 'not_checked' if 'not_checked' in states else 'complies')
    execution=dict(enabled=presence=='yes' and form.get(prefix+'adal_check_execution')=='1',state='not_checked',note='')
    if execution['enabled']:execution['state'],execution['note']=review('adal_execution_state','adal_execution_note')
    return dict(program=ADAL_AZAMAT_META,academic_year_start=year,class_id=class_id,
        class_name=teacher['classes'][class_id]['name'] if class_id else '',presence=presence,compliance=compliance,
        note=note('homeroom_documents_note'),criteria=criteria,execution=execution)
