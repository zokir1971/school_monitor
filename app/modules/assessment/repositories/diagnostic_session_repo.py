"""Scoped diagnostic session queries and bulk snapshot persistence."""
from sqlalchemy import select,func
from app.modules.assessment.models_work_plans import AssessmentWorkPlan as Plan,AssessmentWorkPlanItem as Item
from app.modules.assessment.models_diagnostic_sessions import DiagnosticSession as Session,DiagnosticParticipant as Person
from app.modules.assessment.models_diagnostic_attempts import DiagnosticAttempt as Attempt
from app.modules.assessment.models_diagnostic_preparation import DiagnosticPreparation as Job
from app.modules.education.models import Subject,SchoolClass
from app.modules.assessment.repositories.work_plan_assignment_repo import class_query

async def owned(db,owner_id,session_id,lock=False):
    q=select(Session).where(Session.id==session_id,Session.owner_id==owner_id)
    if lock:q=q.with_for_update().execution_options(populate_existing=True)
    return (await db.execute(q)).scalar_one_or_none()

async def selected_plans(db,owner_id,ids):
    return list((await db.execute(select(Plan).where(Plan.id.in_(ids),Plan.created_by_user_id==owner_id).order_by(Plan.id).with_for_update())).scalars())

async def selected_classes(db,context,year,classes):
    return (await db.execute(class_query(context,year).where(SchoolClass.id.in_(classes)))).all()

async def plan_items(db,ids):
    return list((await db.execute(select(Item).where(Item.work_plan_id.in_(ids)).order_by(Item.work_plan_id,Item.variant_no,Item.order_no))).scalars())

async def subject_names(db,ids):
    return {s.id:s for s in (await db.execute(select(Subject.id,Subject.name_ru,Subject.name_kz).where(Subject.id.in_(ids)))).all()}

async def persist(db,objects=()):
    if objects:db.add_all(objects)
    await db.flush()

async def period_bounds(db,session_id):
    # One aggregate statement, independent of the number of pupils.
    from sqlalchemy import case
    q=select(func.min(Attempt.started_at),func.max(case((Attempt.status=='active',Attempt.deadline_at),else_=None))).join(Person,Person.id==Attempt.participant_id).where(Person.session_id==session_id)
    return (await db.execute(q)).one()

async def prepared_plans(db,owner_id):
    return list((await db.execute(select(Plan).where(Plan.created_by_user_id==owner_id,Plan.status=='prepared').order_by(Plan.id.desc()).limit(100))).scalars())

async def recent(db,owner_id):
    return list((await db.execute(select(Session).where(Session.owner_id==owner_id).order_by(Session.id.desc()).limit(30))).scalars())

async def jobs(db,ids):
    return {j.session_id:j for j in (await db.execute(select(Job).where(Job.session_id.in_(ids)))).scalars()} if ids else {}

async def locked_people(db,session_id):
    return list((await db.execute(select(Person).where(Person.session_id==session_id).order_by(Person.id).with_for_update())).scalars())

async def refresh(db,obj):await db.refresh(obj)
