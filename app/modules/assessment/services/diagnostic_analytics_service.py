"""Finalize diagnostics through the existing completion checks and summary builder.
One school/subject per worker transaction; no duplicate result models.
"""
from collections import defaultdict
import logging
from sqlalchemy.exc import IntegrityError,DataError
from datetime import datetime,timezone
from decimal import Decimal
from types import SimpleNamespace as NS
from app.modules.assessment.repositories import diagnostic_analytics_repo as repo,diagnostic_result_repo as results
from app.modules.assessment.services.diagnostic_session_service import own
from app.modules.assessment.services.assessment_completion_service import AssessmentCompletionService as Completion
from app.modules.assessment.enums import AssessmentCheckpoint,AssessmentParticipationStatus as Participation,AssessmentStatus,AssessmentGrade
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError


MODES={'exclude':('Не включать (пробная сессия)','Қоспау (сынақ сессиясы)'),
       'general':('Только общая аналитика','Тек жалпы талдау'),
       'baseline':('Нулевой контроль','Нөлдік бақылау'),
       **{f'quarter_{n}':(f'{n} четверть',f'{n} тоқсан') for n in range(1,5)},'final':('Итоговая контрольная точка','Қорытынды бақылау нүктесі')}


def options(context):
    context=context or {};t=context.get('work_type')
    keys=['exclude','general']
    if t=='baseline':keys.append('baseline')
    elif context.get('quarter') in (1,2,3,4):
        keys.append('quarter_'+str(context['quarter']))
        if t=='soch' and context['quarter']==4:keys.append('final')
    return [(key,MODES[key]) for key in keys]


async def overview(db,session_id):
    return [dict(row,analytics=(row['assessment_context'] or {}).get('analytics') or {},
        options=options(row['assessment_context'])) for row in await repo.overview(db,session_id)]


async def enqueue(db,user,session_id,values):
    session=await own(db,user,session_id,True)
    if session.status!='closed':raise WorkPlanError('Сначала закройте проведение сессии. / Алдымен сессияны өткізуді жабыңыз.')
    from app.modules.assessment.services.diagnostic_attempt_service import expire
    await expire(db,session_id=session.id)
    counts=await results.publish_counts(db,session.id)
    if counts['active'] or counts['unprocessed'] or counts['pending']:
        raise WorkPlanError('Дождитесь завершения всех начатых работ, подсчёта и ручной проверки. / Басталған жұмыстардың аяқталуын, есептелуін және қолмен тексерілуін күтіңіз.')
    rows=await repo.subjects(db,session.id,True);count=await repo.school_count(db,session.id);prepared=[];checkpoints={}
    if not count:raise WorkPlanError('В сессии нет участников. / Сессияда қатысушылар жоқ.')
    for row in rows:
        mode=values.get('analytics_'+str(row['id']),'exclude')
        if mode not in dict(options(row['assessment_context'])):raise WorkPlanError('Проверьте контрольную точку предмета. / Пәннің бақылау нүктесін тексеріңіз.')
        if mode=='exclude':continue
        context=dict(row['assessment_context'] or {});job=context.get('analytics') or {}
        if job and job.get('mode')!=mode:
            if job.get('processed',0):raise WorkPlanError('Режим уже зафиксирован для этого предмета. / Бұл пәннің режимі бекітілген.')
            job={}
        if job.get('state') in ('queued','completed'):continue
        checkpoint=None if mode=='general' else mode
        if checkpoint:checkpoints[row['id']]=checkpoint
        job=dict(job,mode=mode,state='queued',cursor=job.get('cursor',0),processed=job.get('processed',0),total=count,error=None)
        context['analytics']=job;prepared.append((row['id'],context))
    if not prepared:
        if any((r['assessment_context'] or {}).get('analytics',{}).get('state') in ('queued','completed') for r in rows):return
        raise WorkPlanError('Выберите предмет для включения в аналитику. / Талдауға қосылатын пәнді таңдаңыз.')
    if any((await repo.conflicts_many(db,session.id,checkpoints)).values()):
        raise WorkPlanError('Контрольная точка уже занята другой работой одного из классов. Ручные результаты не заменены. / Бақылау нүктесін сыныптардың біріндегі басқа жұмыс пайдаланған. Қолмен енгізілген нәтижелер өзгертілмеді.')
    await repo.set_contexts(db,prepared)


def assessment_values(session,subject,school_id,variant,language):
    source=subject['assessment_context'] or {};t=source.get('work_type','baseline')
    snapshots=[s for s in subject['snapshots'] if s['variant_no']==variant]
    if not snapshots or any(language not in s['payloads'] for s in snapshots):raise WorkPlanError('Нет замороженного варианта/языка. / Сақталған нұсқа/тіл жоқ.')
    maximum=sum((Decimal(s['max_score']) for s in snapshots),Decimal(0))
    if maximum<=0:raise WorkPlanError('Некорректный максимум баллов. / Ең жоғары балл қате.')
    settings={k:v for k,v in source.items() if k!='analytics'}
    from app.modules.assessment.helpers.assessment_names import names as standard_names,VERSION
    settings[VERSION]=source.get(VERSION) or standard_names(kind=t,subject_kk=subject['name_kk'],subject_ru=subject['name_ru'],
       grades=[session['participant_grade']],year=session['academic_year_start'],quarter=source.get('quarter'),
       track=source.get('education_track'),number=source.get('section_number'))
    return dict(school_id=school_id,diagnostic_subject_id=subject['id'],diagnostic_variant=variant,diagnostic_language=language,
        subject_id=subject['subject_id'],created_by_user_id=session['owner_id'],title=settings[VERSION]['ru'],
        subject_name_snapshot=subject['name_ru' if language=='ru' else 'name_kk'],assessment_type='summative' if t in ('sor','soch') else ('baseline' if t=='baseline' else 'diagnostic'),
        assessment_mode={'sor':'assessment_by_section','soch':'assessment_by_quarter'}.get(t,'by_objectives' if any(s.get('objectives') for s in snapshots) else 'without_objectives'),input_mode='online',status='active',
        max_score=maximum,duration_minutes=subject['minutes'],settings=dict(settings,diagnostic_session_id=session['id'],academic_year_start=session['academic_year_start'],participant_grade=session['participant_grade'],objective_allocation='equal_cents_v1'))


async def finalize_school(db,session,subject,school_id,mode):
    org=await repo.lock_school(db,school_id);checkpoint=None if mode=='general' else mode
    if (session['scope_kind']=='school' and school_id!=session['scope_id']) or (session['scope_kind']=='district' and org['district_id']!=session['scope_id']) or (session['scope_kind']=='region' and org['region_id']!=session['scope_id']):raise WorkPlanError('school_scope_changed')
    if checkpoint and await repo.conflicts(db,session['id'],subject['id'],checkpoint,school_id):raise WorkPlanError('checkpoint_conflict')
    people=await repo.roster(db,session['id'],subject['id'],school_id)
    if not people:raise WorkPlanError('empty_roster')
    assignments={p['id']:p['assignments'][str(subject['source_plan_id'])] for p in people}
    contexts=sorted({(a['variant'],a['language']) for a in assignments.values()})
    for p in people:
        if p['attempt_id'] and (p['attempt_status']=='active' or not p['assessment_student_id']):raise WorkPlanError('pending_results')
    assessments=await repo.ensure_assessments(db,[assessment_values(session,subject,school_id,v,l) for v,l in contexts],subject['id'],school_id,checkpoint)
    from app.modules.assessment.helpers.work_plan_presentation import ordered_items
    from app.modules.assessment.services.diagnostic_result_service import structure
    definitions={}
    for variant,language in contexts:
        selected=[row for row in subject['snapshots'] if row['variant_no']==variant]
        ordered=ordered_items([NS(**row,id=n) for n,row in enumerate(selected)])
        items=[dict(question_type=row.question_type,max_score=str(row.max_score),objectives=row.objectives,payload=row.payloads[language]) for row in ordered]
        definitions[(variant,language)]=structure(items,language)
    await repo.ensure_structure(db,assessments,definitions)
    a_by={(a['diagnostic_variant'],a['diagnostic_language']):a for a in assessments}
    teachers=await repo.teachers(db,school_id,subject['subject_id'],{p['school_class_id'] for p in people})
    teacher_by={}
    for teacher in teachers:
        if teacher['school_class_id'] in teacher_by:raise WorkPlanError('ambiguous_teacher')
        teacher_by[teacher['school_class_id']]=teacher
    groups={}
    for p in people:
        assignment=assignments[p['id']];a=a_by[(assignment['variant'],assignment['language'])];teacher=teacher_by.get(p['school_class_id'])
        key=(a['id'],p['school_class_id'])
        groups[key]=dict(school_id=school_id,assessment_id=a['id'],school_class_id=p['school_class_id'],class_name_snapshot=p['class_label'],
            grade_level_snapshot=session['participant_grade'],academic_year_start_snapshot=session['academic_year_start'],
            teacher_staff_member_id=teacher['staff_member_id'] if teacher else None,teacher_name_snapshot=teacher['teacher_name_snapshot'] if teacher else None)
    group_rows=await repo.ensure_groups(db,list(groups.values()),[a['id'] for a in assessments]);group_by={(g['assessment_id'],g['school_class_id']):g for g in group_rows}
    students=[]
    for p in people:
        assignment=assignments[p['id']];a=a_by[(assignment['variant'],assignment['language'])];g=group_by[(a['id'],p['school_class_id'])]
        students.append(dict(school_id=school_id,assessment_group_id=g['id'],student_id=p['student_id'],student_name_snapshot=p['full_name'],
            participation_status='completed' if p['attempt_id'] else 'not_completed'))
    await repo.ensure_students(db,students)
    participants=await repo.participants(db,[a['id'] for a in assessments]);by_group=defaultdict(list)
    for p in participants:
        result=NS(score=p['score'],max_score=p['max_score'],percent=p['percent'],grade=p['grade']) if p['score'] is not None else None
        by_group[p['assessment_group_id']].append(NS(**{k:p[k] for k in ('id','student_id','student_name_snapshot','participation_status')},result=result))
    at=datetime.now(timezone.utc);graphs=[]
    for a in assessments:
        a=NS(**a);a.status=AssessmentStatus(a.status)
        a.checkpoint=AssessmentCheckpoint(checkpoint) if checkpoint else None
        a.groups=[NS(**g,students=by_group[g['id']]) for g in group_rows if g['assessment_id']==a.id]
        graphs.append(a)
    summaries=Completion.prepare_diagnostic_completion(assessments=graphs,district_id_snapshot=org['district_id'],region_id_snapshot=org['region_id'],calculated_at=at)
    await repo.finish(db,summaries,[a['id'] for a in assessments],at)
    return sum(g['teacher_staff_member_id'] is None for g in group_rows)


async def process_one(db):
    subject=await repo.claim(db)
    if subject is None:return False
    context=dict(subject['assessment_context']);job=dict(context['analytics']);session=await repo.session(db,subject['session_id'])
    school=await repo.next_school(db,session['id'],job['cursor'])
    if school is None:job.update(state='completed',error=None)
    else:
        try:
            async with db.begin_nested():
                if session['status']!='closed':raise WorkPlanError('session_not_closed')
                missing=await finalize_school(db,session,subject,school,job['mode'])
            job.update(cursor=school,processed=job['processed']+1,missing_teacher_groups=job.get('missing_teacher_groups',0)+missing)
        except (WorkPlanError,ValueError,KeyError,TypeError,IntegrityError,DataError) as exc:
            logging.getLogger(__name__).error('Diagnostic analytics stopped: subject=%s school=%s type=%s',subject['id'],school,type(exc).__name__)
            job.update(state='failed',error='checkpoint_conflict' if str(exc)=='checkpoint_conflict' else 'validation_failed',school_id=school)
    context['analytics']=job;await repo.set_context(db,subject['id'],context)
    return True
