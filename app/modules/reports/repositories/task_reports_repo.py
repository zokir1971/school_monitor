# app/modules/reports/repositories/task_reports_repo.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
    SchoolMonthPlanItemReviewPlace,
)
from app.modules.planning.models_school import SchoolPlan
from app.modules.reports.models_documents import (
    TaskExecutionData,
    TaskExecutionSelectedReport,
)
from app.modules.reports.models_report_assignments import (
    TaskSelectedReportAssignment,
)
from app.modules.staff.models_staff_school import (
    SchoolStaffMember,
    SchoolStaffRole,
)
from app.modules.users.models import User


class TaskReportsRepo:
    """
    Repository рабочей страницы отчетов конкретной задачи.

    Здесь находятся только запросы, необходимые для:
    - данных задачи;
    - выбранных отчетов;
    - текущих рабочих документов;
    - мест рассмотрения;
    - текущего сотрудника;
    - назначений отчетов.
    """

    @classmethod
    async def get_task_for_reports_page(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            user_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить задачу для страницы подготовки системных отчетов.

        Проверяет доступ:
        - принадлежность к школе
        - назначение исполнителем
        """

        stmt = (
            select(SchoolMonthPlanItem)
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                SchoolMonthPlanItem.assignees.any(
                    SchoolMonthPlanItemAssignee.staff_role.has(
                        SchoolStaffRole.staff_member.has(
                            SchoolStaffMember.user_account.has(
                                User.id == user_id
                            )
                        )
                    )
                )
            )
            .options(
                selectinload(SchoolMonthPlanItem.assignees)
                .selectinload(SchoolMonthPlanItemAssignee.staff_role)
                .selectinload(SchoolStaffRole.staff_member)
                .selectinload(SchoolStaffMember.user_account),

                selectinload(SchoolMonthPlanItem.source_row11),

                selectinload(SchoolMonthPlanItem.month_plan)
                .selectinload(SchoolMonthPlan.school_plan)
                .selectinload(SchoolPlan.school),
            )
        )
        return await db.scalar(stmt)

    @classmethod
    async def get_selected_report(
            cls,
            db: AsyncSession,
            *,
            selected_report_id: int,
    ) -> TaskExecutionSelectedReport | None:
        """
        Получить выбранный отчет вместе с его типом.
        """
        stmt = (
            select(TaskExecutionSelectedReport)
            .where(
                TaskExecutionSelectedReport.id == selected_report_id
            )
            .options(
                selectinload(
                    TaskExecutionSelectedReport.report_type
                )
            )
        )

        return await db.scalar(stmt)

    @classmethod
    async def get_execution_data_with_selected_reports(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> TaskExecutionData | None:
        """
        Получить execution_data вместе с выбранными отчетами.

        Нужен для промежуточной страницы:
        - какие отчеты выбрал исполнитель;
        - для какого объекта/учителя/класса каждый отчет.
        """

        stmt = (
            select(TaskExecutionData)
            .where(TaskExecutionData.month_item_id == month_item_id)
            .options(
                selectinload(TaskExecutionData.selected_reports).selectinload(
                    TaskExecutionSelectedReport.report_type
                )
            )
        )

        return await db.scalar(stmt)

    @classmethod
    async def list_review_places(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[str]:
        stmt = (
            select(SchoolMonthPlanItemReviewPlace.review_place)
            .where(
                SchoolMonthPlanItemReviewPlace.month_item_id == month_item_id
            )
        )

        result = await db.execute(stmt)

        return list(result.scalars().all())

    @staticmethod
    async def get_current_staff_member_id(
            db: AsyncSession,
            *,
            user_id: int,
    ) -> int | None:
        """
        Получить SchoolStaffMember текущего пользователя.
        """

        stmt = (
            select(SchoolStaffMember.id)
            .where(
                SchoolStaffMember.user_account.has(
                    User.id == user_id
                ),
                SchoolStaffMember.is_active.is_(True),
            )
            .limit(1)
        )

        return await db.scalar(stmt)

    @staticmethod
    async def get_assignment_map(
            db: AsyncSession,
            *,
            selected_report_ids: list[int],
    ) -> dict[int, int]:
        """
        Получить:

            selected_report_id -> staff_member_id
        """

        if not selected_report_ids:
            return {}

        stmt = (
            select(
                TaskSelectedReportAssignment.selected_report_id,
                TaskSelectedReportAssignment.staff_member_id,
            )
            .where(
                TaskSelectedReportAssignment.selected_report_id.in_(
                    selected_report_ids
                )
            )
        )

        rows = (
            await db.execute(stmt)
        ).all()

        return {
            int(row.selected_report_id):
                int(row.staff_member_id)
            for row in rows
        }
