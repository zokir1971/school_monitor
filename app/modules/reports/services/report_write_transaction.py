"""Shared transaction boundary for typed report writes and newly stored files."""
from contextlib import asynccontextmanager
import logging
from sqlalchemy import select
from app.core.storage import get_storage
from app.modules.planning.models_month_plan import SchoolMonthPlanItem, SchoolMonthPlan
from app.modules.planning.models_school import SchoolPlan
from app.modules.reports.models_documents import TaskExecutionData, TaskExecutionSelectedReport
from app.modules.reports.models_report_assignments import TaskSelectedReportAssignment
from app.modules.reports.repositories.document_correction_repo import DocumentCorrectionRepo

logger = logging.getLogger(__name__)

def value(v):
    return getattr(v, "value", v)

async def lock_report_task(db, *, month_item_id, selected_report_id, user):
    I, M, P, E, S, A = [m.__table__ for m in (SchoolMonthPlanItem, SchoolMonthPlan, SchoolPlan,
        TaskExecutionData, TaskExecutionSelectedReport, TaskSelectedReportAssignment)]
    row = (await db.execute(select(I.c.completed_at, I.c.status, M.c.status.label("monthly_status"), P.c.status.label("annual_status"))
        .select_from(I.join(M, M.c.id == I.c.month_plan_id).join(P, P.c.id == M.c.school_plan_id)
            .join(E, E.c.month_item_id == I.c.id).join(S, S.c.execution_data_id == E.c.id))
        .where(I.c.id == month_item_id, S.c.id == selected_report_id, I.c.is_included.is_(True), P.c.school_id == user.school_id)
        .with_for_update(of=I))).mappings().one_or_none()
    if row is None:
        raise ValueError("Отчёт не найден или недоступен.")
    if row['completed_at'] or value(row['status']) in ('done', 'reviewed') or any(value(row[k]) == 'archived' for k in ('monthly_status', 'annual_status')):
        raise ValueError("Завершённую или архивную задачу изменять нельзя.")
    assignment = (await db.execute(select(A.c.staff_member_id, A.c.status).where(A.c.selected_report_id == selected_report_id).with_for_update())).mappings().one_or_none()
    if not assignment or user.staff_member_id is None or assignment['staff_member_id'] != user.staff_member_id or assignment['status'] == 'waived':
        raise ValueError("Отчёт не назначен текущему сотруднику или выполнение отменено.")

@asynccontextmanager
async def report_write_transaction(db):
    created_keys = []
    try:
        yield created_keys
    except BaseException:
        await db.rollback()
        for key in created_keys:
            try:
                # Also protects against a COMMIT that succeeded but lost its reply.
                if not await DocumentCorrectionRepo.referenced(db, key):
                    await get_storage().delete(object_key=key)
            except Exception:
                logger.exception("Could not confirm report file state; preserving file")
        raise

async def delete_unreferenced_report_file(*, db, storage_service, object_key):
    try:
        if not await DocumentCorrectionRepo.referenced(db, object_key):
            await storage_service.delete(object_key=object_key)
    except Exception:
        logger.exception("Could not remove replaced report file")
