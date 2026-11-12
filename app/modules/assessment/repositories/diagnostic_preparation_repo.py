"""Bounded class selection and aggregate enrollment preflight."""
from sqlalchemy import select,func
from app.modules.education.models import SchoolClass,SchoolStudent,SchoolStudentEnrollment as Enrollment
from app.modules.org.models import School,District
from app.modules.assessment.repositories.work_plan_assignment_repo import class_query
from app.modules.assessment.repositories.diagnostic_selection_repo import selection
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError


def enrollment_query(context,year,class_ids):
    allowed=class_query(context,year).subquery()
    return select(SchoolStudent.id.label('student_id')).select_from(Enrollment).join(allowed,
        (allowed.c.id==Enrollment.school_class_id)&(allowed.c.school_id==Enrollment.school_id)).join(SchoolStudent,
        (SchoolStudent.id==Enrollment.student_id)&(SchoolStudent.school_id==Enrollment.school_id)).where(
        allowed.c.id.in_(class_ids),Enrollment.is_active.is_(True),Enrollment.left_at.is_(None),SchoolStudent.is_active.is_(True))


async def enrollment_summary(db,context,year,class_ids):
    q=enrollment_query(context,year,class_ids).subquery()
    row=(await db.execute(select(func.count(),func.count(func.distinct(q.c.student_id))).select_from(q))).one()
    return row[0],row[1]


async def filtered_ids(db,plan,year,values):
    filters=await selection(db,plan,year,values)  # Validates every supplied geographic ID.
    q=class_query(plan,year)
    for column,key in ((District.region_id,'filter_region_id'),(District.id,'filter_district_id'),(School.id,'filter_school_id')):
        if filters[key] is not None:q=q.where(column==filters[key])
    ids=list((await db.execute(select(q.subquery().c.id).order_by('id').limit(5001))).scalars())
    if not 1<=len(ids)<=5000:raise WorkPlanError('По фильтру нужны 1–5000 классов. Сузьте фильтр. / Сүзгі бойынша 1–5000 сынып қажет. Сүзгіні тарылтыңыз.')
    return ids

# Durable-job lifecycle. Only repository functions issue ORM/SQL operations.
from sqlalchemy import insert
from app.modules.assessment.models_diagnostic_preparation import DiagnosticPreparation as Job
from app.modules.assessment.models_diagnostic_sessions import DiagnosticSession as Session,DiagnosticParticipant as Person
from app.modules.users.models import User

async def lock_owner(db,owner_id):
    await db.execute(select(User.id).where(User.id==owner_id).with_for_update())

async def previous_job(db,owner_id,request_key):
    return (await db.execute(select(Job).where(Job.owner_id==owner_id,Job.request_key==request_key))).scalar_one_or_none()

async def user(db,user_id):return await db.get(User,user_id)

async def persist(db,job=None):
    if job is not None:db.add(job)
    await db.flush()

async def insert_people(db,people):
    if people:await db.execute(insert(Person),people)
    await db.flush()

async def claim(db):
    session=(await db.execute(select(Session).join(Job,Job.session_id==Session.id).where(Job.state.in_(('queued','running')))
        .order_by(Job.id).with_for_update(of=Session,skip_locked=True).limit(1))).scalar_one_or_none()
    if session is None:return None,None
    job=(await db.execute(select(Job).where(Job.session_id==session.id).with_for_update())).scalar_one()
    return session,job

async def job(db,session_id,lock=False):
    q=select(Job).where(Job.session_id==session_id)
    if lock:q=q.with_for_update()
    return (await db.execute(q)).scalar_one_or_none()

async def refresh(db,job):await db.refresh(job)

async def code_rows(db,session_id,after):
    return (await db.execute(select(Person.id,Person.student_id,Person.school_name,Person.class_label,Person.full_name).where(
        Person.session_id==session_id,Person.id>after).order_by(Person.id).limit(500))).all()
