"""School-scoped report context/documents. Assessment result queries stay in assessment."""
from sqlalchemy import select,and_,or_,exists,insert,update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.modules.assessment.models import AssessmentTaskLink
from app.modules.planning.models_month_plan import SchoolMonthPlan,SchoolMonthPlanItem,SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlan
from app.modules.staff.models_staff_school import SchoolStaffRole
from app.modules.org.models import School,District
from app.modules.reports.models_documents import TaskExecutionDocument,TaskExecutionData,TaskExecutionSelectedReport,ReportTypeModel
from app.modules.reports.models_report_assignments import TaskSelectedReportAssignment
from app.modules.reports.assessment_report_types import REPORT_TYPES
L=AssessmentTaskLink.__table__
I,N,B,J,D,E,T,Y,X,Z=[m.__table__ for m in (SchoolMonthPlanItem,SchoolMonthPlan,SchoolPlan,SchoolStaffRole,
 TaskExecutionDocument,TaskExecutionData,TaskExecutionSelectedReport,ReportTypeModel,TaskSelectedReportAssignment,SchoolMonthPlanItemAssignee)]
CODE='knowledge_quality_table'

async def context(db, *, task_id, selected_id, user, lock=False, report_code=CODE):
    """Assignment grants edit; task assignees can read. School admin stays school-scoped."""
    if report_code=='analytical_reference':
        from app.modules.reports.repositories.structured_report_repo import final_context
        return await final_context(db,task_id=task_id,selected_id=selected_id,user=user,lock=lock)
    admin=getattr(user.role,'value',user.role)=='school_admin'
    task_assignee=exists(select(Z.c.id).join(J,J.c.id==Z.c.staff_role_id).where(
        Z.c.month_item_id==I.c.id,J.c.staff_member_id==user.staff_member_id,
        J.c.school_id==user.school_id,J.c.is_active.is_(True)))
    access=or_(X.c.staff_member_id==user.staff_member_id,task_assignee,I.c.responsible_user_id==user.id)
    query=(select(T.c.id.label('selected_id'),Y.c.code.label('report_code'),T.c.report_type_id,T.c.target_kind,T.c.target_value,T.c.target_label,
        X.c.staff_member_id.label('assigned_staff_id'),X.c.status.label('assignment_status'),
        I.c.completed_at,I.c.id.label('task_id'),N.c.month.label('month'),N.c.status.label('month_status'),B.c.status.label('annual_status'),E.c.completion_mode,E.c.algorithm_parameters,B.c.academic_year,
        School.__table__.c.name.label('school_name'))
        .select_from(T.join(E,E.c.id==T.c.execution_data_id).join(I,I.c.id==E.c.month_item_id)
            .join(N,N.c.id==I.c.month_plan_id).join(B,B.c.id==N.c.school_plan_id)
            .join(School.__table__,School.__table__.c.id==B.c.school_id)
            .join(Y,Y.c.id==T.c.report_type_id).outerjoin(X,X.c.selected_report_id==T.c.id))
        .where(T.c.id==selected_id,I.c.id==task_id,I.c.is_included.is_(True),
            B.c.school_id==user.school_id,Y.c.code==report_code))
    if not admin:query=query.where(access)
    if lock:query=query.with_for_update(of=I)
    row=(await db.execute(query)).mappings().one_or_none()
    if row is None:return None
    row=dict(row)
    if lock:
        assignment=(await db.execute(select(X).where(X.c.selected_report_id==selected_id).with_for_update())).mappings().one_or_none()
        row['assigned_staff_id']=assignment['staff_member_id'] if assignment else None
        row['assignment_status']=assignment['status'] if assignment else None
    return dict(row,can_edit=bool(admin or row['assigned_staff_id']==user.staff_member_id))


async def document(db,selected_id,*,task_id=None,report_code=CODE):
    if report_code=='analytical_reference':
        return (await db.execute(select(D).where(D.c.month_item_id==task_id,D.c.is_final.is_(True),D.c.is_current.is_(True)).order_by(D.c.id.desc()).limit(1))).mappings().one_or_none()
    return (await db.execute(select(D).where(D.c.selected_report_id==selected_id,D.c.is_final.is_(False),D.c.is_current.is_(True))
        .order_by(D.c.id.desc()).limit(1))).mappings().one_or_none()


async def save_document(db,*,context,user,payload,html,text):
    code=context.get('report_code',CODE)
    config=REPORT_TYPES[code]
    if payload.get('report_code',CODE)!=code:raise ValueError('Report type mismatch')
    doc=await document(db,context['selected_id'],task_id=context['task_id'],report_code=code)
    values=dict(schema_json=payload,custom_content_html=html,custom_content_text=text,report_code=code,report_label=config['title_kk'],report_type_id=context['report_type_id'])
    if doc:
        await db.execute(update(D).where(D.c.id==doc['id']).values(**values));return doc['id']
    values.update(month_item_id=context['task_id'],selected_report_id=None if config.get('final') else context['selected_id'],
        document_type='reference' if config.get('final') else 'report',source='generated',status='draft',version=1,is_current=True,is_final=bool(config.get('final')),
        uploaded_by_user_id=user.id,template_mode='standard',title=config['title_ru'])
    return (await db.execute(insert(D).values(**values).returning(D.c.id))).scalar_one()


async def link_assessments(db,task_id,assessment_ids,user_id):
    statement=pg_insert if db.bind.dialect.name=='postgresql' else sqlite_insert
    if assessment_ids:
        await db.execute(statement(L).values([dict(assessment_id=a,month_item_id=task_id,link_type='primary',linked_by_user_id=user_id)
            for a in sorted(set(assessment_ids))]).on_conflict_do_nothing(index_elements=['assessment_id','month_item_id']))


async def submit_document(db,doc_id,selected_id,user_id,at,stored):
    await db.execute(update(D).where(D.c.id==doc_id).values(status='submitted',submitted_by_user_id=user_id,submitted_at=at,
        file_path=stored.object_key,stored_file_name=stored.stored_file_name,original_file_name=stored.original_file_name,
        mime_type=stored.content_type,file_size=stored.file_size))
    if selected_id:
        await db.execute(update(X).where(X.c.selected_report_id==selected_id).values(status='completed',waived_reason=None,waived_at=None,waived_by_user_id=None))


async def document_by_id(db,doc_id,report_code=CODE):
    kind = D.c.report_code == report_code
    if report_code == 'analytical_reference':
        # The final-document page can also show a file uploaded by the executor.
        # Such files have no system report code; retain their original metadata.
        kind = or_(kind, and_(D.c.is_final.is_(True), D.c.is_current.is_(True),
            D.c.source == 'upload', or_(D.c.report_code.is_(None), D.c.report_code == '')))
    return (await db.execute(select(D).where(D.c.id == doc_id, kind))).mappings().one_or_none()


async def storage_context(db,task_id,school_id):
    from app.core.storage.schemas import SchoolStorageContext
    school=School.__table__;district=District.__table__
    row=(await db.execute(select(district.c.region_id,school.c.district_id,school.c.id.label('school_id'),
        B.c.academic_year,B.c.id.label('school_plan_id'),I.c.id.label('month_item_id'))
        .select_from(I.join(N,N.c.id==I.c.month_plan_id).join(B,B.c.id==N.c.school_plan_id)
            .join(school,school.c.id==B.c.school_id).join(district,district.c.id==school.c.district_id))
        .where(I.c.id==task_id,school.c.id==school_id))).mappings().one_or_none()
    if row is None:raise ValueError('Storage context not found')
    return SchoolStorageContext(**row)



async def replace_pdf_file(db,previous,stored):
    """Compare-and-swap file metadata only; preserve content and all lifecycle fields."""
    changed=(await db.execute(update(D).where(D.c.id==previous['id'],D.c.is_current.is_(True),
        D.c.file_path==previous['file_path'],D.c.status==previous['status'])
        .values(file_path=stored.object_key,stored_file_name=stored.stored_file_name,
            original_file_name=stored.original_file_name,mime_type=stored.content_type,file_size=stored.file_size)
        .returning(D.c.id))).scalar_one_or_none()
    return changed is not None


async def inspection_sources(db, *, school_id, task_id, teacher_ids=None, sections=None):
    """One scoped batch: selected positions, assignments and current typed reports."""
    from app.modules.reports.models_template_reports import LessonObservationReport, CheckingNotebooksReport
    O,Q=LessonObservationReport.__table__,CheckingNotebooksReport.__table__
    latest=(select(D.c.id).where(D.c.selected_report_id==T.c.id,D.c.month_item_id==task_id,D.c.is_current.is_(True),D.c.is_final.is_(False))
        .order_by(D.c.id.desc()).limit(1).correlate(T).scalar_subquery())
    query=(select(T.c.id.label('selected_id'),T.c.target_kind,T.c.target_value,T.c.target_label,Y.c.code,
        X.c.status.label('assignment_status'),D.c.id.label('document_id'),D.c.status.label('document_status'),D.c.schema_json['summary'].label('reading_summary'),D.c.schema_json['max_score'].label('lesson_max'),
        O.c.total.label('lesson_score'),O.c.class_name.label('lesson_class'),O.c.lesson_datetime.label('lesson_date'),
        O.c.feedback.label('lesson_feedback'),Q.c.total_score.label('notebook_score'),Q.c.max_score.label('notebook_max'),
        Q.c.rows_json['class_checks_version'].label('notebook_checks_version'),Q.c.rows_json['class_checks'].label('notebook_checks'),
        Q.c.class_name.label('notebook_class'),Q.c.check_date.label('notebook_date'),Q.c.conclusion.label('notebook_conclusion'))
        .select_from(T.join(E,E.c.id==T.c.execution_data_id).join(I,I.c.id==E.c.month_item_id)
            .join(N,N.c.id==I.c.month_plan_id).join(B,B.c.id==N.c.school_plan_id).join(Y,Y.c.id==T.c.report_type_id)
            .outerjoin(X,X.c.selected_report_id==T.c.id).outerjoin(D,D.c.id==latest)
            .outerjoin(O,O.c.task_execution_document_id==D.c.id).outerjoin(Q,Q.c.task_execution_document_id==D.c.id))
        .where(I.c.id==task_id,B.c.school_id==school_id,Y.c.code.in_(['lesson_observation','checking_notebooks_table','reading_speed_table']))
        .order_by(T.c.id).limit(2001))
    if sections is not None:
        codes = {'lessons': 'lesson_observation', 'notebooks': 'checking_notebooks_table', 'reading': 'reading_speed_table'}
        query = query.where(Y.c.code.in_([codes[key] for key in sections if key in codes]))
    if teacher_ids is not None:
        query = query.where(or_(Y.c.code == 'reading_speed_table', and_(
            T.c.target_kind.in_(['teacher', 'primary_teacher']), T.c.target_value.in_([str(tid) for tid in teacher_ids]))))
    return [dict(row) for row in (await db.execute(query)).mappings()]


async def new_final_draft(db, *, previous, user):
    """Keep the signed file/token as history; only the new draft becomes current."""
    payload=dict(previous['schema_json'],revision=1)
    payload.pop('signed_by',None)
    payload.pop('signed_at',None)
    await db.execute(update(D).where(D.c.id==previous['id']).values(is_current=False))
    return (await db.execute(insert(D).values(month_item_id=previous['month_item_id'],
        document_type='reference',source='generated',status='draft',is_final=True,is_current=True,
        version=previous['version']+1,report_code='analytical_reference',report_label=previous['report_label'],
        title=previous['title'],schema_json=payload,uploaded_by_user_id=user.id,template_mode='standard')
        .returning(D.c.id))).scalar_one()
