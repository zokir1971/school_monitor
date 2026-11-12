"""Bounded, school-scoped batch reads for the remaining system reports.

No ORM lazy loads; no query is issued per pupil, employee or source report.
"""
from sqlalchemy import select, exists, or_, func
from app.modules.reports.repositories.assessment_report_repo import I,N,B,J,D,E,T,Y,X,Z
from app.modules.education.models import SchoolClass, SchoolStudent, SchoolStudentEnrollment
from app.modules.staff.models_staff_school import SchoolStaffMember
from app.modules.org.models import School


async def final_context(db, *, task_id, selected_id, user, lock=False):
    if selected_id!=0:return None  # Explicit final-document route, never a selected position.
    S=School.__table__
    membership=select(Z.c.id).join(J,J.c.id==Z.c.staff_role_id).where(
        Z.c.month_item_id==I.c.id,J.c.school_id==user.school_id,
        J.c.staff_member_id==user.staff_member_id,J.c.is_active.is_(True))
    primary=exists(membership.where(Z.c.assignment_kind=='primary'))
    admin=getattr(user.role,'value',user.role)=='school_admin'
    query=(select(I.c.id.label('task_id'),I.c.completed_at,N.c.month,N.c.status.label('month_status'),
        B.c.status.label('annual_status'),B.c.academic_year,S.c.name.label('school_name'),E.c.algorithm_parameters,E.c.completion_mode,
        primary.label('is_primary')).select_from(I.join(N,N.c.id==I.c.month_plan_id).join(B,B.c.id==N.c.school_plan_id)
        .join(S,S.c.id==B.c.school_id).join(E,E.c.month_item_id==I.c.id))
        .where(I.c.id==task_id,B.c.school_id==user.school_id,I.c.is_included.is_(True)))
    if not admin:query=query.where(or_(exists(membership),I.c.responsible_user_id==user.id))
    if lock:query=query.with_for_update(of=I)
    row=(await db.execute(query)).mappings().one_or_none()
    if row is None:return None
    editable=bool(admin or row['is_primary'])
    return dict(row,selected_id=0,report_code='analytical_reference',report_type_id=None,
        target_kind='complex',target_value=str(task_id),target_label=(row['algorithm_parameters'] or {}).get('context_label') or str(task_id),
        can_edit=editable,assigned_staff_id=user.staff_member_id if editable else None,assignment_status=None)


async def classes(db,school_id,year):
    C=SchoolClass.__table__
    rows=(await db.execute(select(C.c.id,C.c.grade_level,C.c.letter).where(C.c.school_id==school_id,
        C.c.academic_year_start==year,C.c.is_active.is_(True)).order_by(C.c.grade_level,C.c.letter,C.c.id).limit(1001))).mappings()
    return [dict(row,name=str(row['grade_level'])+(row['letter'] or '')) for row in rows]


async def roster(db,school_id,year,class_ids,as_of):
    C,P,A=SchoolClass.__table__,SchoolStudent.__table__,SchoolStudentEnrollment.__table__
    # EXISTS avoids duplicating a pupil when historical enrollment intervals overlap.
    enrolled=exists(select(A.c.id).where(A.c.student_id==P.c.id,A.c.school_id==school_id,
        A.c.school_class_id==C.c.id,A.c.enrolled_at<=as_of,or_(A.c.left_at.is_(None),A.c.left_at>=as_of)))
    query=(select(P.c.id,P.c.last_name,P.c.first_name,P.c.middle_name,C.c.id.label('class_id'),C.c.grade_level,C.c.letter)
        .select_from(C.join(P,P.c.school_id==C.c.school_id)).where(C.c.school_id==school_id,C.c.academic_year_start==year,
            C.c.id.in_(class_ids),C.c.grade_level.between(1,4),enrolled)
        .order_by(C.c.grade_level,C.c.letter,P.c.last_name,P.c.first_name,P.c.id).limit(2001))
    return [dict(id=row['id'],class_id=row['class_id'],class_name=str(row['grade_level'])+(row['letter'] or ''),
        name=' '.join(row[k] for k in ('last_name','first_name','middle_name') if row[k]),state='pending',words='',errors='',seconds='',comprehension='not_checked',note='')
        for row in (await db.execute(query)).mappings()]


async def staff(db,school_id):
    S=SchoolStaffMember.__table__
    return [dict(row) for row in (await db.execute(select(S.c.id,S.c.full_name,func.substr(S.c.position_text,1,160).label('position_text'))
        .where(S.c.school_id==school_id,S.c.is_active.is_(True)).order_by(S.c.full_name,S.c.id).limit(2001))).mappings()]


async def referenced_documents(db,school_id,document_ids):
    if not document_ids:return {}
    query=(select(D.c.id,D.c.title,D.c.report_code,D.c.status,D.c.version,D.c.month_item_id)
        .select_from(D.join(I,I.c.id==D.c.month_item_id).join(N,N.c.id==I.c.month_plan_id).join(B,B.c.id==N.c.school_plan_id))
        .where(B.c.school_id==school_id,D.c.id.in_(document_ids),D.c.is_current.is_(True)))
    return {row['id']:dict(row) for row in (await db.execute(query)).mappings()}


async def evidence(db,school_id,task_id):
    """One query, JSON projections only (no pupil arrays or report HTML)."""
    from app.modules.reports.models_template_reports import LessonObservationReport,CheckingNotebooksReport
    O,Q=LessonObservationReport.__table__,CheckingNotebooksReport.__table__
    latest=(select(D.c.id).where(D.c.selected_report_id==T.c.id,D.c.month_item_id==task_id,
        D.c.is_current.is_(True),D.c.is_final.is_(False)).order_by(D.c.id.desc()).limit(1).correlate(T).scalar_subquery())
    query=(select(T.c.id.label('selected_id'),T.c.target_label,Y.c.code,Y.c.name_ru.label('type_label_ru'),Y.c.name_kz.label('type_label_kk'),
        X.c.status.label('assignment_status'),D.c.id.label('document_id'),D.c.status.label('document_status'),
        D.c.version,D.c.submitted_at,D.c.schema_json['revision'].label('revision'),
        D.c.schema_json['summary'].label('summary'),D.c.schema_json['totals'].label('totals'),
        O.c.total.label('score'),Q.c.total_score.label('notebook_score'),Q.c.max_score.label('notebook_max'),
        D.c.schema_json['max_score'].label('max_score'),
        func.substr(func.coalesce(func.nullif(D.c.schema_json['conclusion'].as_string(),''),O.c.feedback,Q.c.conclusion,''),1,2000).label('finding'))
        .select_from(T.join(E,E.c.id==T.c.execution_data_id).join(I,I.c.id==E.c.month_item_id)
            .join(N,N.c.id==I.c.month_plan_id).join(B,B.c.id==N.c.school_plan_id).join(Y,Y.c.id==T.c.report_type_id)
            .outerjoin(X,X.c.selected_report_id==T.c.id).outerjoin(D,D.c.id==latest)
            .outerjoin(O,O.c.task_execution_document_id==D.c.id).outerjoin(Q,Q.c.task_execution_document_id==D.c.id))
        .where(I.c.id==task_id,B.c.school_id==school_id,Y.c.code!='analytical_reference').order_by(T.c.id).limit(2001))
    return [dict(row) for row in (await db.execute(query)).mappings()]
