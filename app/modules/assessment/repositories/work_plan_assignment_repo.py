"""Set-based organization, class and enrollment access. No per-pupil queries."""
from sqlalchemy import select, exists, func
from app.modules.education.models import SchoolClass, SchoolStudent, SchoolStudentEnrollment
from app.modules.org.models import School, District
from app.modules.assessment.models_work_assignments import AssessmentWorkAssignment as Assignment, AssessmentWorkParticipant as Participant

def class_query(plan, year):
    query = select(SchoolClass.id, SchoolClass.school_id, SchoolClass.grade_level,
        SchoolClass.letter, SchoolClass.instruction_language, School.name.label('school_name')).join(
        School, School.id == SchoolClass.school_id).join(District, District.id == School.district_id).where(
        SchoolClass.academic_year_start == year, SchoolClass.grade_level == plan.participant_grade,
        SchoolClass.is_active.is_(True))
    if plan.scope_kind == 'school': query = query.where(School.id == plan.school_id)
    elif plan.scope_kind == 'district': query = query.where(District.id == plan.district_id)
    else: query = query.where(District.region_id == plan.region_id)
    if plan.participant_grade in (10,11) and plan.education_track in ('emn','ogn'):
        query = query.where(SchoolClass.education_track == plan.education_track)
    return query

async def selected_class_ids(db,plan,year,ids,lock=False):
    query=class_query(plan,year).where(SchoolClass.id.in_(ids)).order_by(SchoolClass.id)
    if lock:query=query.with_for_update(of=[SchoolClass,School,District])
    return {row.id for row in (await db.execute(query)).all()}

async def classes(db, plan, year, after=0):
    return (await db.execute(class_query(plan, year).where(SchoolClass.id > after).order_by(SchoolClass.id).limit(101))).all()

async def enrolled(db, plan, year, class_ids, lock=False, limit=5001):
    allowed = class_query(plan, year).subquery()
    query = select(SchoolStudent.id.label('student_id'), SchoolStudent.last_name,
        SchoolStudent.first_name, SchoolStudent.middle_name, allowed.c.id.label('class_id'),
        allowed.c.school_id, allowed.c.grade_level, allowed.c.letter, allowed.c.instruction_language,
        allowed.c.school_name).select_from(SchoolStudentEnrollment).join(allowed,
        (allowed.c.id == SchoolStudentEnrollment.school_class_id) & (allowed.c.school_id == SchoolStudentEnrollment.school_id)).join(
        SchoolStudent, (SchoolStudent.id == SchoolStudentEnrollment.student_id) &
        (SchoolStudent.school_id == SchoolStudentEnrollment.school_id)).where(
        allowed.c.id.in_(class_ids), SchoolStudentEnrollment.is_active.is_(True),
        SchoolStudentEnrollment.left_at.is_(None), SchoolStudent.is_active.is_(True)).order_by(
        allowed.c.id, SchoolStudent.last_name, SchoolStudent.first_name, SchoolStudent.id).limit(limit)
    if lock: query = query.with_for_update(of=[SchoolStudentEnrollment, SchoolStudent])
    return (await db.execute(query)).all()

async def has_assignments(db, plan_id):
    return bool(await db.scalar(select(exists().where(Assignment.work_plan_id == plan_id))))

async def existing_students(db, plan_id, ids):
    return set((await db.execute(select(Participant.student_id).where(
        Participant.work_plan_id == plan_id, Participant.student_id.in_(ids)))).scalars().all())

async def variant_counts(db, plan_id, class_ids):
    return (await db.execute(select(Participant.school_class_id, Participant.variant_no, func.count().label('total')).where(
        Participant.work_plan_id == plan_id, Participant.school_class_id.in_(class_ids)).group_by(
        Participant.school_class_id, Participant.variant_no))).all()

async def roster(db, plan_id, after=0):
    return (await db.execute(select(Participant).where(Participant.work_plan_id==plan_id, Participant.id>after)
        .order_by(Participant.id).limit(101))).scalars().all()

async def participant(db, plan_id, participant_id):
    return (await db.execute(select(Participant).where(Participant.work_plan_id==plan_id,Participant.id==participant_id))).scalar_one_or_none()
