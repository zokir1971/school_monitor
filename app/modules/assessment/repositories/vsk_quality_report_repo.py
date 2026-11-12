"""Batch assessment data for report consumers; no report document lifecycle here."""
from sqlalchemy import tuple_
from sqlalchemy import select,and_,or_,exists,func,cast,String
from app.modules.assessment.models import Assessment,AssessmentGroup,AssessmentStudent,AssessmentResult,AssessmentObjective,AssessmentObjectiveResult
from app.modules.education.models import SchoolClass,Subject,SchoolClassSubjectTeacher,SchoolSubjectSubgroupMember
from app.modules.staff.models_staff_school import SchoolStaffMember
A,G,P,R,O,V=[m.__table__ for m in (Assessment,AssessmentGroup,AssessmentStudent,AssessmentResult,AssessmentObjective,AssessmentObjectiveResult)]
C,S,H,M=[m.__table__ for m in (SchoolClass,Subject,SchoolClassSubjectTeacher,SchoolSubjectSubgroupMember)]
F=SchoolStaffMember.__table__

async def reference_data(db,school_id,year):
    classes=list((await db.execute(select(C.c.id,(cast(C.c.grade_level,String)+C.c.letter).label("name"),C.c.grade_level,C.c.education_track)
        .where(C.c.school_id==school_id,C.c.academic_year_start==year)
        .order_by(C.c.grade_level,C.c.letter,C.c.id))).mappings())
    subjects=list((await db.execute(select(S.c.id,S.c.name_ru,S.c.name_kz).where(exists(
        select(A.c.id).join(G,and_(G.c.assessment_id==A.c.id,G.c.school_id==school_id))
        .where(A.c.school_id==school_id,A.c.subject_id==S.c.id,A.c.status=='completed',G.c.academic_year_start_snapshot==year)))
        .order_by(S.c.sort_order,S.c.id))).mappings())
    return classes,subjects


async def teacher_name(db,school_id,teacher_id):
    return (await db.execute(select(F.c.full_name).where(F.c.id==teacher_id,F.c.school_id==school_id))).scalar_one_or_none()


def student_scope(school_id,teacher_id):
    if teacher_id is None:return P.c.school_id==school_id
    # EXISTS avoids multiplying pupils for duplicate/secondary teaching assignments.
    # Closed historical assignments still count for their academic year's dated work.
    on_date=func.coalesce(func.date(A.c.scheduled_at),func.date(A.c.started_at),func.date(A.c.created_at))
    membership=exists(select(M.c.id).where(M.c.school_id==school_id,M.c.subgroup_id==H.c.subgroup_id,
        M.c.student_id==P.c.student_id,or_(M.c.is_active.is_(True),M.c.left_at.is_not(None)),
        or_(M.c.joined_at.is_(None),func.date(M.c.joined_at)<=on_date),or_(M.c.left_at.is_(None),func.date(M.c.left_at)>=on_date)).correlate(P,A,H))
    teaches=exists(select(H.c.id).where(H.c.school_id==school_id,H.c.school_class_id==G.c.school_class_id,
        H.c.subject_id==A.c.subject_id,H.c.staff_member_id==teacher_id,
        or_(H.c.assigned_at.is_(None),H.c.assigned_at<=on_date),
        or_(H.c.unassigned_at.is_(None),H.c.unassigned_at>=on_date),
        # Inactive undated legacy assignments cannot establish historical scope.
        or_(H.c.is_active.is_(True),H.c.unassigned_at.is_not(None)),
        or_(H.c.subgroup_id.is_(None),membership)).correlate(P,A,G))
    return and_(P.c.school_id==school_id,teaches)


def source(school_id,year,teacher_id=None):
    joined=G.join(A,and_(A.c.id==G.c.assessment_id,A.c.school_id==school_id)).join(
        C,and_(C.c.id==G.c.school_class_id,C.c.school_id==school_id)).join(
        S,S.c.id==A.c.subject_id).join(P,and_(P.c.assessment_group_id==G.c.id,student_scope(school_id,teacher_id)))
    joined=joined.outerjoin(R,R.c.assessment_student_id==P.c.id)
    return joined,[G.c.school_id==school_id,G.c.academic_year_start_snapshot==year,A.c.status=='completed']


async def candidates(db,*,school_id,year,teacher_id=None,subject_id=None,subject_ids=(),subject_class_pairs=None,grade=None,class_ids=(),checkpoint="",date_from=None,date_to=None):
    joined,conditions=source(school_id,year,teacher_id)
    if subject_class_pairs is not None:conditions.append(tuple_(A.c.subject_id,G.c.school_class_id).in_([(p['subject_id'],p['class_id']) for p in subject_class_pairs]))
    if subject_ids:conditions.append(A.c.subject_id.in_(subject_ids))
    if subject_id:conditions.append(A.c.subject_id==subject_id)
    if grade:conditions.append(G.c.grade_level_snapshot==grade)
    if class_ids:conditions.append(G.c.school_class_id.in_(class_ids))
    if checkpoint:conditions.append(A.c.checkpoint==checkpoint)
    if date_from:conditions.append(func.date(A.c.completed_at)>=date_from)
    if date_to:conditions.append(func.date(A.c.completed_at)<=date_to)
    # Page complete logical works, never a slice of their variant rows.
    work_id=func.coalesce(A.c.diagnostic_subject_id,-A.c.id)
    pending_a=A.alias('pending_variant_assessment');pending_g=G.alias('pending_variant_group')
    pending=exists(select(pending_g.c.id).join(pending_a,pending_a.c.id==pending_g.c.assessment_id).where(
        pending_g.c.school_id==school_id,pending_a.c.school_id==school_id,
        pending_g.c.academic_year_start_snapshot==year,pending_g.c.school_class_id==G.c.school_class_id,
        pending_a.c.subject_id==A.c.subject_id,pending_a.c.diagnostic_subject_id==A.c.diagnostic_subject_id,
        pending_a.c.status!='completed')).correlate(A,G)
    conditions.append(or_(A.c.diagnostic_subject_id.is_(None),~pending))
    works=(select(work_id.label('work_id'),G.c.school_class_id.label('class_id'),A.c.subject_id.label('subject_id'),
        func.min(A.c.completed_at).label('completed_at'))
        .select_from(joined).where(*conditions).group_by(work_id,G.c.school_class_id,A.c.subject_id)
        .order_by(func.min(A.c.completed_at),A.c.subject_id,G.c.school_class_id,work_id).limit(201).cte('report_work_choices'))
    all_rows,all_conditions=source(school_id,year,teacher_id)
    all_rows=all_rows.join(works,and_(work_id==works.c.work_id,G.c.school_class_id==works.c.class_id,A.c.subject_id==works.c.subject_id))
    query=(select(G.c.id.label('group_id'),A.c.id.label('assessment_id'),A.c.title,A.c.settings['standard_name_v1'].label('titles'),
        A.c.subject_id,S.c.name_ru,S.c.name_kz,G.c.school_class_id.label('class_id'),
        G.c.class_name_snapshot.label('class_name'),G.c.grade_level_snapshot.label('grade'),
        C.c.education_track,A.c.checkpoint,A.c.completed_at,A.c.max_score,A.c.diagnostic_subject_id,func.count(P.c.id).label('students'))
        .select_from(all_rows).where(*all_conditions).group_by(G.c.id,A.c.id,S.c.id,C.c.id,works.c.completed_at,works.c.work_id)
        .order_by(works.c.completed_at,S.c.id,G.c.school_class_id,works.c.work_id,A.c.id,G.c.id).limit(10001))

    return [dict(row) for row in (await db.execute(query)).mappings()]


async def aggregates(db,*,school_id,year,group_ids,teacher_id=None):
    joined,conditions=source(school_id,year,teacher_id)
    conditions.append(G.c.id.in_(group_ids))
    eligible=and_(R.c.id.is_not(None),P.c.participation_status.not_in(['absent','excused','not_completed']))
    columns=[G.c.id.label('group_id'),func.count(P.c.id).label('total_students'),
        func.count(R.c.id).filter(eligible).label('participated_students'),
        func.max(R.c.score).filter(eligible).label('highest_score'),
        func.coalesce(func.sum(R.c.score).filter(eligible),0).label('score_sum'),
        func.coalesce(func.sum(R.c.percent).filter(eligible),0).label('percent_sum')]
    columns += [func.count(P.c.id).filter(P.c.participation_status==status).label(status+'_students')
        for status in ['absent','excused','not_completed']]
    columns += [func.count(R.c.id).filter(and_(eligible,R.c.grade==str(grade))).label('grade_'+str(grade)+'_count')
        for grade in [2,3,4,5]]
    return [dict(row) for row in (await db.execute(select(*columns).select_from(joined).where(*conditions).group_by(G.c.id))).mappings()]


async def objectives(db,*,school_id,year,group_ids,teacher_id=None):
    joined,conditions=source(school_id,year,teacher_id)
    conditions += [G.c.id.in_(group_ids),P.c.participation_status.not_in(['absent','excused','not_completed'])]
    joined=joined.join(V,V.c.assessment_result_id==R.c.id).join(O,and_(O.c.id==V.c.assessment_objective_id,O.c.assessment_id==A.c.id))
    query=(select(G.c.id.label('group_id'),O.c.learning_objective_id,O.c.code_snapshot.label('code'),O.c.title_snapshot.label('title'),
        func.count(V.c.id).label('students'),func.sum(V.c.score).label('score_sum'),func.sum(V.c.max_score).label('max_sum'))
        .select_from(joined).where(*conditions).group_by(G.c.id,O.c.id).order_by(G.c.id,O.c.order_no))
    return [dict(row) for row in (await db.execute(query)).mappings()]


async def teacher_references(db,school_id,year,teacher_id,subject_id=None):
    classes,subjects=await reference_data(db,school_id,year)
    assignments=list((await db.execute(select(H.c.school_class_id,H.c.subject_id)
        .join(C,and_(C.c.id==H.c.school_class_id,C.c.school_id==school_id))
        .where(H.c.school_id==school_id,H.c.staff_member_id==teacher_id,C.c.academic_year_start==year,
            or_(H.c.is_active.is_(True),H.c.unassigned_at.is_not(None))))).mappings())
    return ([c for c in classes if c['id'] in {a['school_class_id'] for a in assignments if not subject_id or a['subject_id']==subject_id}],
        [s for s in subjects if s['id'] in {a['subject_id'] for a in assignments}])

