"""One school-scoped query for selected reports, assignments and current documents."""
from sqlalchemy import select,and_,or_,exists
from app.modules.planning.models_month_plan import SchoolMonthPlan,SchoolMonthPlanItem,SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlan,SchoolPlanRow11
from app.modules.staff.models_staff_school import SchoolStaffRole,SchoolStaffMember
from app.modules.reports.models_documents import TaskExecutionSelectedReport,TaskExecutionData,ReportTypeModel,TaskExecutionDocument
from app.modules.reports.models_report_assignments import TaskSelectedReportAssignment

I,M,P,R,A,H,F,T,E,Y,D,X=[c.__table__ for c in (
 SchoolMonthPlanItem,SchoolMonthPlan,SchoolPlan,SchoolPlanRow11,SchoolMonthPlanItemAssignee,
 SchoolStaffRole,SchoolStaffMember,TaskExecutionSelectedReport,TaskExecutionData,ReportTypeModel,TaskExecutionDocument,TaskSelectedReportAssignment)]


def query(*,school_id,staff_member_id,month=None,month_item_id=None,mine_only=False):
    primary=exists(select(A.c.id).join(H,H.c.id==A.c.staff_role_id).where(A.c.month_item_id==I.c.id,
        A.c.assignment_kind=='primary',H.c.staff_member_id==staff_member_id,H.c.school_id==school_id,H.c.is_active.is_(True)))
    latest=(select(D.c.id).where(D.c.selected_report_id==T.c.id,D.c.is_final.is_(False),D.c.is_current.is_(True))
        .order_by(D.c.id.desc()).limit(1).correlate(T).scalar_subquery())
    stmt=(select(I.c.id.label('month_item_id'),I.c.planned_start,I.c.planned_end,I.c.status.label('task_status'),I.c.completed_at,
        R.c.topic,T.c.id.label('selected_report_id'),T.c.target_label,Y.c.code.label('report_code'),Y.c.name_ru,Y.c.name_kz,
        X.c.staff_member_id.label('assigned_staff_id'),X.c.status.label('assignment_status'),F.c.full_name.label('assigned_to'),
        D.c.id.label('document_id'),D.c.status.label('document_status'),D.c.source.label('document_source'),D.c.file_path,
        E.c.completion_mode,M.c.status.label('monthly_status'),P.c.status.label('annual_status'),primary.label('is_primary'))
        .select_from(T.join(E,E.c.id==T.c.execution_data_id).join(I,I.c.id==E.c.month_item_id)
            .join(M,M.c.id==I.c.month_plan_id).join(P,P.c.id==M.c.school_plan_id).join(Y,Y.c.id==T.c.report_type_id)
            .outerjoin(R,R.c.id==I.c.source_row11_id).outerjoin(X,X.c.selected_report_id==T.c.id)
            .outerjoin(F,and_(F.c.id==X.c.staff_member_id,F.c.school_id==school_id)).outerjoin(D,D.c.id==latest))
        .where(P.c.school_id==school_id,I.c.is_included.is_(True),or_(primary,X.c.staff_member_id==staff_member_id)))
    if mine_only:stmt=stmt.where(X.c.staff_member_id==staff_member_id)
    if month is not None:stmt=stmt.where(M.c.month==month)
    if month_item_id is not None:stmt=stmt.where(I.c.id==month_item_id)
    return stmt.order_by(I.c.planned_start.asc().nulls_last(),I.c.id,Y.c.sort_order,Y.c.id,T.c.id)


class MyReportCatalogRepo:
    @staticmethod
    async def list_reports(db,*,school_id,staff_member_id,month,page=1,page_size=20):
        return list((await db.execute(query(school_id=school_id,staff_member_id=staff_member_id,month=month,mine_only=True).offset((page-1)*page_size).limit(page_size+1))).mappings())

    @staticmethod
    async def has_task_access(db,*,school_id,staff_member_id,month_item_id):
        stmt=query(school_id=school_id,staff_member_id=staff_member_id,month_item_id=month_item_id).with_only_columns(I.c.id).limit(1)
        return (await db.execute(stmt)).first() is not None
