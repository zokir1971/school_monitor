"""Connect immutable finished attempts to existing canonical result models."""
import copy,hashlib,json
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal
from types import SimpleNamespace
from app.modules.assessment.helpers.diagnostic_scoring import decode,grade,split_score,final_scores,Totals
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError
from app.modules.assessment.repositories import diagnostic_result_repo as repo


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),default=str).encode()).hexdigest()


def frozen_items(attempt,subject,assignment):
    items=copy.deepcopy(attempt['private_data']['items'])
    selected=[s for s in subject['snapshots'] if s['variant_no']==assignment['variant']]
    from app.modules.assessment.helpers.work_plan_presentation import ordered_items
    ordered=ordered_items([SimpleNamespace(**s,id=n) for n,s in enumerate(selected)])
    selected=[selected[s.id] for s in ordered]
    if len(items)!=len(selected):raise ValueError('snapshot_length')
    for item,row in zip(items,selected):
        if 'objectives' not in item:
            # Before this extension the frozen subject, not the live bank, supplies goals.
            if fingerprint(item['payload'])!=fingerprint(row['payloads'][assignment['language']]):raise ValueError('snapshot_mismatch')
            item['objectives']=copy.deepcopy(row.get('objectives',[]))
    return items


def structure(items,language="ru"):
    goals={};maximums=defaultdict(Decimal);questions=[]
    for n,item in enumerate(items,1):
        p=item['payload'];maximum=Decimal(item['max_score'])
        objectives={int(o['id']):o for o in item.get('objectives',[]) if o.get('id')}
        ids=sorted(objectives)
        for oid,share in zip(ids,split_score(maximum,len(ids))):
            if share>0:
                goals[oid]=objectives[oid];maximums[oid]+=share
        snapshot=dict(text_segments=p.get('text_segments',[]),explanation=p.get('explanation'),objective_ids=ids,fingerprint=fingerprint(item))
        questions.append(dict(question_type=item['question_type'],text=p.get('text') or '',instruction=p.get('instruction'),
            max_score=maximum,order_no=n,content=p['content'],answer_key=p['answer_key'],grading_settings=p.get('grading_settings') or {},
            diagnostic_snapshot=snapshot,is_active=True,is_required=True))
    objectives=[dict(learning_objective_id=oid,code_snapshot=str(goals[oid].get('code',oid)),
        title_snapshot=str(goals[oid].get('title_ru' if language=='ru' else 'title_kz') or goals[oid].get('title_ru') or goals[oid].get('title_kz') or goals[oid].get('code',oid)),
        max_score=maximums[oid],order_no=n) for n,oid in enumerate(sorted(goals),1)]
    return questions,objectives


async def calculate_total(db,sid,answers,at):
    score=final_scores(answers)
    if score is None:return
    goals=await repo.goal_rows(db,sid)
    by_learning={g['learning_objective_id']:g for g in goals}
    scores=defaultdict(Decimal)
    for answer in answers:
        ids=answer['diagnostic_snapshot']['objective_ids']
        for oid,part in zip(ids,split_score(answer['score'],len(ids))):scores[oid]+=part
    values=[]
    for oid,g in by_learning.items():
        # Rounding of split points is deterministic at both max and earned sides.
        value=min(scores[oid],g['max_score'])
        values.append(dict(assessment_objective_id=g['id'],score=value,max_score=g['max_score'],
            percent=Totals.calculate_percent(score=value,max_score=g['max_score'])))
    await repo.write_total(db,sid,score,values,at)


async def process(db,attempt_id):
    context=await repo.context(db,attempt_id,True)
    if not context:return False
    attempt,person,subject,session=context
    if attempt['status']=='active' or attempt['assessment_student_id'] is not None:return False
    assignment=person['assignments'][str(subject['source_plan_id'])]
    items=frozen_items(attempt,subject,assignment)
    questions,objectives=structure(items,assignment['language']);maximum=sum((q['max_score'] for q in questions),Decimal(0))
    at=datetime.now(timezone.utc)
    source=subject.get('assessment_context') or {}
    work_type=source.get('work_type','baseline')
    from app.modules.assessment.helpers.assessment_names import names as standard_names,VERSION
    work_names=source.get(VERSION) or standard_names(kind=work_type,subject_kk=subject['name_kk'],subject_ru=subject['name_ru'],
        grades=[session['participant_grade']],year=session['academic_year_start'],quarter=source.get('quarter'),
        track=source.get('education_track'),number=source.get('section_number'))
    source=dict(source,standard_name_v1=work_names)
    assessment=dict(school_id=person['school_id'],diagnostic_subject_id=subject['id'],diagnostic_variant=assignment['variant'],
        diagnostic_language=assignment['language'],subject_id=subject['subject_id'],created_by_user_id=session['owner_id'],
        title=work_names['ru'],
        subject_name_snapshot=subject['name_ru'] if assignment['language']=='ru' else subject['name_kk'],
        assessment_type='summative' if work_type in ('sor','soch') else ('baseline' if work_type=='baseline' else 'diagnostic'),
        assessment_mode={'sor':'assessment_by_section','soch':'assessment_by_quarter'}.get(work_type,'by_objectives' if objectives else 'without_objectives'),
        checkpoint=None,input_mode='online',status='active',max_score=maximum,
        duration_minutes=subject['minutes'],settings=dict(source,diagnostic_session_id=session['id'],academic_year_start=session['academic_year_start'],
            participant_grade=session['participant_grade'],objective_allocation='equal_cents_v1'))
    group=dict(school_id=person['school_id'],school_class_id=person['school_class_id'],class_name_snapshot=person['class_label'],
        grade_level_snapshot=session['participant_grade'],academic_year_start_snapshot=session['academic_year_start'])
    student=dict(school_id=person['school_id'],student_id=person['student_id'],student_name_snapshot=person['full_name'],
        participation_status='submitted',started_at=attempt['started_at'],completed_at=attempt['submitted_at'])
    sid,saved,goals=await repo.create_structure(db,assessment,group,student,questions,objectives)
    if len(saved)!=len(items) or any(q['diagnostic_snapshot']['fingerprint']!=fingerprint(i) for q,i in zip(saved,items)):
        raise ValueError('immutable_snapshot_conflict')
    private={**attempt['private_data'],'items':items}
    decoded=decode(private,attempt['responses'])
    answers=[dict(question_id=q['id'],**grade(item,data)) for q,item,data in zip(saved,items,decoded)]
    await repo.write_answers(db,sid,answers)
    answers=await repo.answer_rows(db,sid)
    await calculate_total(db,sid,answers,at)
    await repo.link(db,attempt_id,sid)
    return True


async def manual_score(db,user,attempt_id,answer_id,value):
    from app.modules.assessment.services.diagnostic_session_service import own
    context=await repo.context(db,attempt_id)
    if not context:raise WorkPlanError('Работа не найдена. / Жұмыс табылмады.')
    attempt,person,subject,session=context
    session=await own(db,user,session['id'],True)
    # Lock session before attempt, same order as organizer close/pupil save.
    context=await repo.context(db,attempt_id,True);attempt=context[0]
    if session.results_published_at:raise WorkPlanError('Результаты уже опубликованы. / Нәтижелер жарияланған.')
    sid=attempt['assessment_student_id']
    if not sid:raise WorkPlanError('Дождитесь подсчёта. / Есептеуді күтіңіз.')
    answers=await repo.answer_rows(db,sid)
    answer=next((a for a in answers if a['id']==answer_id),None)
    try:score=Decimal(str(value).replace(',','.'))
    except Exception:raise WorkPlanError('Проверьте балл. / Баллды тексеріңіз.') from None
    if answer is None or not score.is_finite() or not 0<=score<=answer['max_score'] or score!=score.quantize(Decimal('.01')):
        raise WorkPlanError('Балл должен быть от 0 до максимума, не более двух знаков после запятой. / Балл 0-ден ең жоғары баллға дейін болуы керек.')
    at=datetime.now(timezone.utc)
    if not await repo.manual(db,sid,answer_id,score,user.id,at):raise WorkPlanError('Ответ уже проверен. Обновите страницу. / Жауап тексерілген. Бетті жаңартыңыз.')
    await calculate_total(db,sid,await repo.answer_rows(db,sid),at)


async def publish(db,user,session_id):
    from app.modules.assessment.services.diagnostic_session_service import own
    from app.modules.assessment.services.diagnostic_attempt_service import now,utc,expire
    session=await own(db,user,session_id,True);at=await now(db)
    if session.results_published_at:return
    if session.status!='closed' and (not session.closes_at or utc(session.closes_at)>at):
        raise WorkPlanError('Сначала закройте проведение или дождитесь конца периода. / Алдымен өткізуді жабыңыз немесе кезеңнің аяқталуын күтіңіз.')
    await expire(db,session_id=session.id)
    counts=await repo.publish_counts(db,session.id)
    if not counts['attempts'] or counts['active'] or counts['unprocessed'] or counts['pending']:
        raise WorkPlanError('Завершите подсчёт и ручную проверку всех начатых работ. / Басталған барлық жұмысты есептеу мен қолмен тексеруді аяқтаңыз.')
    await repo.publish(db,session.id,at)
