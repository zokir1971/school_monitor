"""Bounded scalar metadata for co-executor task lists; no per-task SQL."""
from dataclasses import dataclass, field

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import AssignmentKind
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlan
from app.modules.staff.models_staff_school import SchoolStaffMember, SchoolStaffRole
from app.modules.reports.models_documents import TaskExecutionData, TaskExecutionSelectedReport
from app.modules.reports.models_report_assignments import TaskSelectedReportAssignment


@dataclass(frozen=True, slots=True)
class PrimaryExecutor:
    staff_member_id: int
    full_name: str
    position_text: str | None


@dataclass(slots=True)
class CoExecutorListContext:
    primary_by_task: dict[int, PrimaryExecutor] = field(default_factory=dict)
    report_counts: dict[tuple[int, int], int] = field(default_factory=dict)


class TaskListRepo:
    BATCH_SIZE = 400

    @classmethod
    async def co_executor_context(
        cls, db: AsyncSession, *, school_id: int,
        staff_member_by_task: dict[int, int | None],
    ) -> CoExecutorListContext:
        context = CoExecutorListContext()
        task_ids = list(staff_member_by_task)
        for offset in range(0, len(task_ids), cls.BATCH_SIZE):
            ids = task_ids[offset:offset + cls.BATCH_SIZE]
            primary_query = (select(
                SchoolMonthPlanItemAssignee.month_item_id,
                SchoolStaffMember.id.label('staff_member_id'),
                SchoolStaffMember.full_name, SchoolStaffMember.position_text,
            ).select_from(SchoolMonthPlanItemAssignee)
                .join(SchoolStaffRole, SchoolStaffRole.id == SchoolMonthPlanItemAssignee.staff_role_id)
                .join(SchoolStaffMember, SchoolStaffMember.id == SchoolStaffRole.staff_member_id)
                .join(SchoolMonthPlanItem, SchoolMonthPlanItem.id == SchoolMonthPlanItemAssignee.month_item_id)
                .join(SchoolMonthPlan, SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id)
                .join(SchoolPlan, SchoolPlan.id == SchoolMonthPlan.school_plan_id)
                .where(
                    SchoolMonthPlanItemAssignee.month_item_id.in_(ids),
                    SchoolMonthPlanItemAssignee.assignment_kind == AssignmentKind.PRIMARY,
                    SchoolPlan.school_id == school_id,
                    SchoolStaffRole.school_id == school_id, SchoolStaffRole.is_active.is_(True),
                    SchoolStaffMember.school_id == school_id, SchoolStaffMember.is_active.is_(True),
                ))
            for row in (await db.execute(primary_query)).all():
                primary = PrimaryExecutor(
                    int(row.staff_member_id), str(row.full_name or '—'),
                    str(row.position_text) if row.position_text else None,
                )
                previous = context.primary_by_task.get(row.month_item_id)
                # Preserve the existing Python casefold/id tie-break, including
                # damaged data with several primary roles or duplicate roles.
                if previous is None or (primary.full_name.casefold(), primary.staff_member_id) < (
                    previous.full_name.casefold(), previous.staff_member_id
                ):
                    context.primary_by_task[row.month_item_id] = primary

            members = sorted({member for key in ids if (member := staff_member_by_task[key]) is not None})
            if not members:
                continue
            count_query = (select(
                TaskExecutionData.month_item_id, TaskSelectedReportAssignment.staff_member_id,
                func.count(TaskSelectedReportAssignment.id).label('report_count'),
            ).select_from(TaskSelectedReportAssignment)
                .join(TaskExecutionSelectedReport, TaskExecutionSelectedReport.id == TaskSelectedReportAssignment.selected_report_id)
                .join(TaskExecutionData, TaskExecutionData.id == TaskExecutionSelectedReport.execution_data_id)
                .join(SchoolMonthPlanItem, SchoolMonthPlanItem.id == TaskExecutionData.month_item_id)
                .join(SchoolMonthPlan, SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id)
                .join(SchoolPlan, SchoolPlan.id == SchoolMonthPlan.school_plan_id)
                .where(TaskExecutionData.month_item_id.in_(ids),
                    SchoolPlan.school_id == school_id,
                    TaskSelectedReportAssignment.staff_member_id.in_(members))
                .group_by(TaskExecutionData.month_item_id, TaskSelectedReportAssignment.staff_member_id))
            # Count all assignment statuses, exactly as count_reports_for_staff.
            for row in (await db.execute(count_query)).all():
                if staff_member_by_task[row.month_item_id] == row.staff_member_id:
                    context.report_counts[(row.month_item_id, row.staff_member_id)] = int(row.report_count)
        return context
