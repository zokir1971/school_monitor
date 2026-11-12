"""Canonical results bridge. Core bulk operations; no SQL in presentation/services.
All question/answer/objective writes are batched, independent of question count.
"""
from sqlalchemy import select, update, func, case, and_, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.modules.assessment.models import (Assessment,AssessmentGroup,AssessmentStudent,AssessmentQuestion,
    AssessmentObjective,AssessmentStudentAnswer,AssessmentResult,AssessmentObjectiveResult)
from app.modules.assessment.models_diagnostic_attempts import DiagnosticAttempt
from app.modules.assessment.models_diagnostic_sessions import DiagnosticParticipant,DiagnosticSession,DiagnosticSubject
from app.modules.education.models import SchoolClass,SchoolStudent
A=Assessment.__table__;G=AssessmentGroup.__table__;S=AssessmentStudent.__table__
Q=AssessmentQuestion.__table__;O=AssessmentObjective.__table__;B=AssessmentStudentAnswer.__table__
R=AssessmentResult.__table__;V=AssessmentObjectiveResult.__table__
T=DiagnosticAttempt.__table__;P=DiagnosticParticipant.__table__;D=DiagnosticSubject.__table__;C=DiagnosticSession.__table__


def insert(db,table):
    return (pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert)(table)


async def ensure(db,table,values,keys):
    stmt=insert(db,table).values(**values).on_conflict_do_nothing(index_elements=keys).returning(table.c.id)
    found=(await db.execute(stmt)).scalar_one_or_none()
    if found is not None:return found
    return (await db.execute(select(table.c.id).where(*(table.c[k]==values[k] for k in keys)))).scalar_one()


async def next_attempt(db):
    return (await db.execute(select(T.c.id).where(T.c.status.in_(['submitted','expired']),
        T.c.assessment_student_id.is_(None),T.c.grading_error.is_(None)).order_by(T.c.id).limit(1)
        .with_for_update(skip_locked=True))).scalar_one_or_none()


async def context(db,attempt_id,lock=False):
    q=select(T).where(T.c.id==attempt_id)
    if lock:q=q.with_for_update()
    attempt=(await db.execute(q)).mappings().one_or_none()
    if attempt is None:return None
    # Frozen roster determines school; verify both class and pupil boundaries.
    person=(await db.execute(select(P,SchoolClass.__table__.c.school_id).join(SchoolClass.__table__,SchoolClass.__table__.c.id==P.c.school_class_id)
        .join(SchoolStudent.__table__,and_(SchoolStudent.__table__.c.id==P.c.student_id,
              SchoolStudent.__table__.c.school_id==SchoolClass.__table__.c.school_id)).where(P.c.id==attempt['participant_id']))).mappings().one()
    subject=(await db.execute(select(D).where(D.c.id==attempt['diagnostic_subject_id'],D.c.session_id==person['session_id']))).mappings().one()
    session=(await db.execute(select(C).where(C.c.id==person['session_id']))).mappings().one()
    return attempt,person,subject,session


async def create_structure(db,assessment,group,student,questions,objectives):
    aid=await ensure(db,A,assessment,['diagnostic_subject_id','school_id','diagnostic_variant','diagnostic_language'])
    group={**group,'assessment_id':aid};gid=await ensure(db,G,group,['assessment_id','school_class_id'])
    sid=await ensure(db,S,{**student,'assessment_group_id':gid},['assessment_group_id','student_id'])
    if objectives:
        stmt=insert(db,O).values([{**o,'assessment_id':aid} for o in objectives])
        await db.execute(stmt.on_conflict_do_nothing(index_elements=['assessment_id','learning_objective_id']))
    goals=list((await db.execute(select(O).where(O.c.assessment_id==aid).order_by(O.c.order_no))).mappings())
    by_learning={o['learning_objective_id']:o['id'] for o in goals}
    values=[]
    for q in questions:
        ids=q['diagnostic_snapshot']['objective_ids']
        values.append({**q,'assessment_id':aid,'assessment_objective_id':by_learning.get(ids[0]) if len(ids)==1 else None})
    if values:
        await db.execute(insert(db,Q).values(values).on_conflict_do_nothing(index_elements=['assessment_id','order_no']))
    saved=list((await db.execute(select(Q).where(Q.c.assessment_id==aid).order_by(Q.c.order_no))).mappings())
    return sid,saved,goals


async def write_answers(db,sid,answers):
    if not answers:return
    stmt=insert(db,B).values([{**a,'assessment_student_id':sid} for a in answers])
    # Initial transfer only; replay cannot erase a human review.
    await db.execute(stmt.on_conflict_do_nothing(index_elements=['assessment_student_id','question_id']))


async def answer_rows(db,sid):
    return list((await db.execute(select(B,Q.c.diagnostic_snapshot,Q.c.order_no).join(Q,Q.c.id==B.c.question_id)
        .where(B.c.assessment_student_id==sid).order_by(Q.c.order_no))).mappings())


async def goal_rows(db,sid):
    return list((await db.execute(select(O).join(G,G.c.assessment_id==O.c.assessment_id)
        .join(S,S.c.assessment_group_id==G.c.id).where(S.c.id==sid).order_by(O.c.order_no))).mappings())


async def write_total(db,sid,score,goals,at):
    values=dict(assessment_student_id=sid,score=score.score,max_score=score.max_score,percent=score.percent,grade=score.grade,calculated_at=at)
    stmt=insert(db,R).values(**values)
    rid=(await db.execute(stmt.on_conflict_do_update(index_elements=['assessment_student_id'],set_={k:v for k,v in values.items() if k!='assessment_student_id'}).returning(R.c.id))).scalar_one()
    if goals:
        values=[dict(assessment_result_id=rid,**o) for o in goals]
        stmt=insert(db,V).values(values)
        await db.execute(stmt.on_conflict_do_update(index_elements=['assessment_result_id','assessment_objective_id'],set_={k:stmt.excluded[k] for k in ('score','max_score','percent')}))
    await db.execute(update(S).where(S.c.id==sid).values(participation_status='completed'))


async def link(db,attempt_id,sid):
    await db.execute(update(T).where(T.c.id==attempt_id).values(assessment_student_id=sid,grading_error=None))


async def fail(db,attempt_id):
    await db.execute(update(T).where(T.c.id==attempt_id,T.c.assessment_student_id.is_(None)).values(grading_error='processing_failed'))


async def total(db,sid):
    return (await db.execute(select(R).where(R.c.assessment_student_id==sid))).mappings().one_or_none()


async def manual(db,sid,answer_id,score,user_id,at):
    # Parent attempt lock in service serializes manual reviews and publication.
    result=await db.execute(update(B).where(B.c.id==answer_id,B.c.assessment_student_id==sid,B.c.status=='pending_review')
        .values(score=score,status='checked',is_correct=(score==B.c.max_score),checked_by_user_id=user_id,checked_at=at))
    return result.rowcount==1


async def publish_counts(db,session_id):
    return (await db.execute(select(func.count(T.c.id).label('attempts'),
        func.sum(case((T.c.status=='active',1),else_=0)).label('active'),
        func.sum(case((and_(T.c.status!='active',T.c.assessment_student_id.is_(None)),1),else_=0)).label('unprocessed'),
        func.sum(case((and_(T.c.assessment_student_id.is_not(None),R.c.id.is_(None)),1),else_=0)).label('pending'))
        .select_from(T.join(P,P.c.id==T.c.participant_id).outerjoin(R,R.c.assessment_student_id==T.c.assessment_student_id))
        .where(P.c.session_id==session_id))).mappings().one()


async def publish(db,session_id,at):
    await db.execute(update(C).where(C.c.id==session_id,C.c.results_published_at.is_(None)).values(results_published_at=at))


async def retry(db,session_id):
    await db.execute(update(T).where(T.c.participant_id.in_(select(P.c.id).where(P.c.session_id==session_id)),
        T.c.assessment_student_id.is_(None)).values(grading_error=None))


async def page_results(db,person_ids):
    if not person_ids:return {}
    rows=(await db.execute(select(T.c.id,T.c.participant_id,T.c.diagnostic_subject_id,T.c.assessment_student_id,T.c.grading_error,
        R.c.score,R.c.max_score,R.c.percent,R.c.grade).outerjoin(R,R.c.assessment_student_id==T.c.assessment_student_id)
        .where(T.c.participant_id.in_(person_ids)))).mappings()
    return {(r['participant_id'],r['diagnostic_subject_id']):dict(r) for r in rows}


async def explanation_review_rows(db, *, session_id, subject_id, lock=False):
    """Canonical question annotations for one closed diagnostic, without pupil data."""
    query=select(C.c.status).where(C.c.id==session_id)
    if lock:query=query.with_for_update()
    status=(await db.execute(query)).scalar_one_or_none()
    if status!='closed':raise ValueError('Explanation review requires a closed diagnostic session.')
    query=(select(Q.c.id,Q.c.question_type,Q.c.content,Q.c.answer_key,Q.c.grading_settings,Q.c.max_score,Q.c.diagnostic_snapshot)
           .select_from(Q.join(A,A.c.id==Q.c.assessment_id).join(D,D.c.id==A.c.diagnostic_subject_id))
           .where(D.c.session_id==session_id,D.c.subject_id==subject_id).order_by(Q.c.id))
    if lock:query=query.with_for_update(of=Q)
    return [dict(row) for row in (await db.execute(query)).mappings()]


async def save_explanation_reviews(db, updates):
    """Only the annotation JSON changes; keys, grading and earned results are untouched."""
    if not updates:return
    from sqlalchemy import bindparam
    await db.execute(update(Q).where(Q.c.id==bindparam('review_question_id')).values(diagnostic_snapshot=bindparam('review_snapshot')),updates)
