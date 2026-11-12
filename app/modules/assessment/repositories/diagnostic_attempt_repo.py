"""SQL and persistence for diagnostic attempts; lock ordering stays Session -> Person -> Attempt."""
from datetime import datetime,timezone
from sqlalchemy import select,update,func,or_
from app.modules.assessment.models_diagnostic_sessions import DiagnosticSession as Session,DiagnosticParticipant as Person,DiagnosticSubject as Subject
from app.modules.assessment.models_diagnostic_attempts import DiagnosticAttempt as Attempt

async def clock(db):
    if db.bind.dialect.name=='postgresql':return (await db.execute(select(func.clock_timestamp()))).scalar_one()
    return datetime.now(timezone.utc)

async def identity_session(db,identity):
    return (await db.execute(select(Person.session_id).where(Person.id==identity.get('person'),Person.access_hash==identity.get('hash')))).scalar_one_or_none()

async def authorized_session(db,session_id,lock=False):
    q=select(Session).where(Session.id==session_id,or_(Session.status=='prepared',Session.results_published_at.is_not(None)))
    if lock:q=q.with_for_update(read=True)
    return (await db.execute(q)).scalar_one_or_none()

async def identity_person(db,identity,lock=False):
    q=select(Person).where(Person.id==identity['person'],Person.access_hash==identity['hash'])
    if lock:q=q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()

async def expire(db,at,participant_id=None,session_id=None):
    q=update(Attempt).where(Attempt.status=='active',Attempt.deadline_at<=at)
    if participant_id is not None:q=q.where(Attempt.participant_id==participant_id)
    if session_id is not None:q=q.where(Attempt.participant_id.in_(select(Person.id).where(Person.session_id==session_id)))
    await db.execute(q.values(status='expired',submitted_at=Attempt.deadline_at,version=Attempt.version+1).execution_options(synchronize_session=False))

async def subjects(db,session_id):
    return list((await db.execute(select(Subject.id,Subject.source_plan_id,Subject.name_ru,Subject.name_kk,Subject.minutes,Subject.order_no).where(Subject.session_id==session_id).order_by(Subject.order_no,Subject.id))).all())

async def attempt_states(db,participant_id):
    return {a.diagnostic_subject_id:a for a in (await db.execute(select(Attempt.id,Attempt.diagnostic_subject_id,Attempt.status).where(Attempt.participant_id==participant_id))).all()}

async def session(db,session_id):return await db.get(Session,session_id)

async def subject(db,subject_id,session_id):
    return (await db.execute(select(Subject).where(Subject.id==subject_id,Subject.session_id==session_id))).scalar_one()

async def owned_attempt(db,attempt_id,participant_id,lock=False):
    q=select(Attempt).where(Attempt.id==attempt_id,Attempt.participant_id==participant_id)
    if lock:q=q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()

async def save(db,attempt=None):
    if attempt is not None:db.add(attempt)
    await db.flush()

async def login_person(db,access_hash):
    return (await db.execute(select(Person).join(Session,Session.id==Person.session_id).where(Person.access_hash==access_hash,or_(Session.status=='prepared',Session.results_published_at.is_not(None))))).scalar_one_or_none()

async def subject_info(db,subject_id):
    return (await db.execute(select(Subject.id,Subject.source_plan_id,Subject.name_ru,Subject.name_kk,Subject.assessment_context).where(Subject.id==subject_id))).one()
