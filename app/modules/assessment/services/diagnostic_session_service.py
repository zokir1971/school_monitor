"""Bulk roster/snapshot preparation. No User creation and no AI requests."""
import copy,secrets,hashlib
from collections import Counter
from app.modules.assessment.repositories import diagnostic_session_repo as repo
from app.modules.assessment.models_diagnostic_sessions import DiagnosticSession as Session,DiagnosticSubject as Subject,DiagnosticParticipant as Person
from app.modules.assessment.repositories import work_plan_repo as plans
from app.modules.assessment.repositories import work_plan_assignment_repo as roster
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError,integer,participant_language,completeness
from app.modules.assessment.services.work_plan_service import validate_shared_copies

def digest(code):return hashlib.sha256(code.replace('-','').replace(' ','').upper().encode()).hexdigest()
def access_code():return ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(16))
async def own(db,user,session_id,lock=False):
    session=await repo.owned(db,user.id,session_id,lock)
    options=await plans.scope_options(db,user)
    if session is None or (session.scope_kind,session.scope_id) not in {(s['kind'],s['id']) for s in options}:raise WorkPlanError('Комплект не найден или недоступен.')
    return session
async def create(db,user,values,plan_ids,class_ids,*,prepare_only=False):
    from app.modules.assessment.services.diagnostic_attempt_service import now
    from app.modules.assessment.helpers.diagnostic_period import parse_period
    opening,closing=parse_period(values,await now(db))
    ids=[integer(v,1,2147483647) for v in plan_ids]
    if not 1<=len(ids)<=10 or len(set(ids))!=len(ids):raise WorkPlanError('Выберите от 1 до 10 разных комплектов.')
    year=integer(values.get('year'),2000,2100)
    classes=sorted({integer(v,1,2147483647) for v in class_ids})
    if not 1<=len(classes)<=(5000 if prepare_only else 100):raise WorkPlanError('Выберите от 1 до 5000 классов. / 1–5000 сынып таңдаңыз.' if prepare_only else 'Выберите от 1 до 100 классов.')
    # Session names are generated below from validated work parameters.
    found=await repo.selected_plans(db,user.id,ids)
    if len(found)!=len(ids):raise WorkPlanError('Комплект не найден или недоступен.')
    by_id={r.id:r for r in found};selected=[by_id[i] for i in ids];first=selected[0]
    scope=(first.scope_kind,getattr(first,first.scope_kind+'_id'))
    allowed={(s['kind'],s['id']) for s in await plans.scope_options(db,user)}
    if scope not in allowed:raise WorkPlanError('Выберите доступную область проведения.')
    if any(r.status!='prepared' or r.participant_grade!=first.participant_grade or (r.scope_kind,getattr(r,r.scope_kind+'_id'))!=scope for r in selected):
        raise WorkPlanError('Нужны подготовленные комплекты одной параллели и области проведения.')
    if len({r.subject_id for r in selected})!=len(selected):raise WorkPlanError('Для каждого предмета выберите один комплект.')
    tracks={r.education_track for r in selected if r.education_track in ('emn','ogn')}
    if len(tracks)>1:raise WorkPlanError('Направления комплектов не совпадают.')
    from types import SimpleNamespace
    context=SimpleNamespace(**{k:getattr(first,k,None) for k in ('scope_kind','school_id','district_id','region_id','participant_grade','education_track')})
    if tracks:context.education_track=next(iter(tracks))
    if await roster.selected_class_ids(db,context,year,classes,True)!=set(classes):raise WorkPlanError('Классы не соответствуют параллели или области проведения.')
    if prepare_only:
        from app.modules.assessment.repositories.diagnostic_preparation_repo import enrollment_summary
        total,distinct=await enrollment_summary(db,context,year,classes)
        if not 1<=total<=100000 or distinct!=total:
            raise WorkPlanError('Нужны 1–100000 учеников без повторных зачислений. / Қайталанбайтын 1–100000 оқушы қажет.')
        pupils=await repo.selected_classes(db,context,year,classes)
    else:
        pupils=await roster.enrolled(db,context,year,classes,True)
    if not prepare_only and (not 1<=len(pupils)<=5000 or len({r.student_id for r in pupils})!=len(pupils)):raise WorkPlanError('Нужны от 1 до 5000 учеников без повторных зачислений.')
    saved=await repo.plan_items(db,ids)
    names_by_id=await repo.subject_names(db,[r.subject_id for r in selected])
    from app.modules.assessment.helpers.assessment_names import names as standard_names
    work_names={}
    for plan in selected:
        if plan.academic_year_start is not None and plan.academic_year_start!=year:
            raise WorkPlanError('Учебный год комплекта и проведения не совпадает. / Жинақ пен өткізу оқу жылы сәйкес емес.')
        subject=names_by_id[plan.subject_id]
        work_names[plan.id]=standard_names(kind=plan.work_type,subject_kk=subject.name_kz,subject_ru=subject.name_ru,
           grades=[plan.participant_grade],year=year,quarter=plan.quarter,track=plan.education_track,number=plan.section_number)
    names=work_names[first.id] if len(selected)==1 else {
        'ru':f'Онлайн-оценивание · {first.participant_grade} класс · {year}–{year+1} · Предметов: {len(selected)}',
        'kk':f'Онлайн бағалау · {first.participant_grade} сынып · {year}–{year+1} · Пәндер: {len(selected)}'}
    minutes={r.id:integer(values.get('minutes_'+str(r.id),30),1,240) for r in selected}
    instruction_languages={p.instruction_language for p in pupils}
    if not instruction_languages.issubset({'kz','ru','uz','ug','tg'}):raise WorkPlanError('Укажите язык обучения у всех выбранных классов.')
    for plan in selected:
        rows=[i for i in saved if i.work_plan_id==plan.id]
        if completeness(plan,rows):raise WorkPlanError('Структура вариантов комплекта не завершена.')
        validate_shared_copies(rows)
        for instruction_language in instruction_languages:
            lang=participant_language(plan.language_policy,instruction_language)
            if any(lang not in row.payloads for row in rows):raise WorkPlanError('Нет сохранённой версии на выбранном языке.')
    session=Session(owner_id=user.id,title_ru=names['ru'],title_kk=names['kk'],scope_kind=scope[0],scope_id=scope[1],participant_grade=first.participant_grade,academic_year_start=year,status='closed' if prepare_only else 'prepared',opens_at=opening,closes_at=closing)
    await repo.persist(db,[session]);objects=[]
    for order,plan in enumerate(selected,1):
        subject=names_by_id[plan.subject_id]
        snapshots=[dict(variant_no=i.variant_no,order_no=i.order_no,question_type=i.question_type,difficulty=i.difficulty,max_score=str(i.max_score),objectives=copy.deepcopy(i.objectives),payloads=copy.deepcopy(i.payloads)) for i in saved if i.work_plan_id==plan.id]
        objects.append(Subject(session_id=session.id,source_plan_id=plan.id,subject_id=plan.subject_id,order_no=order,minutes=minutes[plan.id],name_ru=subject.name_ru or subject.name_kz,name_kk=subject.name_kz,snapshots=snapshots,assessment_context=dict(work_type=plan.work_type,quarter=plan.quarter,curriculum_grade=plan.curriculum_grade,education_track=plan.education_track,
            section_number=plan.section_number,standard_name_v1=work_names[plan.id])))
    if prepare_only:
        await repo.persist(db,objects)
        spec=dict(classes=classes,context={k:getattr(context,k,None) for k in ('scope_kind','school_id','district_id','region_id','participant_grade','education_track')},
                  plans=[dict(id=r.id,variant_count=r.variant_count,language_policy=r.language_policy,
                      languages=sorted(set.intersection(*(set(i.payloads) for i in saved if i.work_plan_id==r.id)))) for r in selected],expected_pupils=total)
        return session,spec
    counts=Counter();credentials=[]
    for pupil in pupils:
        assignments={}
        for plan in selected:
            lowest=min(counts[(pupil.class_id,plan.id,v)] for v in range(1,plan.variant_count+1))
            variant=secrets.choice([v for v in range(1,plan.variant_count+1) if counts[(pupil.class_id,plan.id,v)]==lowest])
            counts[(pupil.class_id,plan.id,variant)]+=1
            assignments[str(plan.id)]=dict(variant=variant,language=participant_language(plan.language_policy,pupil.instruction_language))
        raw=access_code();name=' '.join(s for s in (pupil.last_name,pupil.first_name,pupil.middle_name) if s)
        objects.append(Person(session_id=session.id,student_id=pupil.student_id,school_class_id=pupil.class_id,full_name=name,class_label=f'{pupil.grade_level}{pupil.letter}',school_name=pupil.school_name,access_hash=digest(raw),assignments=assignments))
        credentials.append((pupil.school_name,f'{pupil.grade_level}{pupil.letter}',name,'-'.join(raw[i:i+4] for i in range(0,16,4))))
    await repo.persist(db,objects);return session,credentials


async def update_period(db,user,session_id,values):
    from app.modules.assessment.helpers.diagnostic_period import parse_period,utc
    from app.modules.assessment.services.diagnostic_attempt_service import now
    session=await own(db,user,session_id,True)
    if session.status!='prepared':raise WorkPlanError('Закрытая сессия недоступна для изменения. / Жабық сессияны өзгерту мүмкін емес.')
    opening,closing=parse_period(values,await now(db))
    first,last=await repo.period_bounds(db,session.id)
    if (first and opening>utc(first)) or (last and closing<utc(last)):
        raise WorkPlanError('Период не должен исключать начало уже начатых работ или сокращать время активной попытки. / Кезең басталған жұмыстарды алып тастамауы және белсенді әрекеттің уақытын қысқартпауы керек.')
    session.opens_at=opening;session.closes_at=closing
    await repo.persist(db);return session
