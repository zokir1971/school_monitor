# app/modules/tasks/task_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import case, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload, raiseload

from app.modules.planning.enums import (
    AssignmentKind,
    PlanItemStatus,
    PlanStatus,
)
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
)
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11
from app.modules.staff.models_staff_school import SchoolStaffRole


class StaffTasksRepo:
    """
    Репозиторий задач сотрудника.

    Правила доступа:

    - список «Мои задачи» содержит PRIMARY и CO_EXECUTOR;
    - изменение общего статуса задачи разрешено только PRIMARY;
    - основная страница исполнения доступна только PRIMARY.
    """

    @staticmethod
    def _normalize_role_ids(
        staff_role_ids: Sequence[int],
    ) -> list[int]:
        """
        Удалить дубли и привести идентификаторы ролей к int.
        """

        return list(
            dict.fromkeys(
                int(role_id)
                for role_id in staff_role_ids
            )
        )

    @staticmethod
    def _staff_assignee_exists(
        staff_role_ids: Sequence[int],
        *,
        assignment_kinds: Sequence[AssignmentKind] | None = None,
    ):
        """
        Проверить назначение сотрудника на задачу хотя бы через
        одну из его активных должностных ролей.

        Если assignment_kinds не передан, подходят любые назначения:
        PRIMARY и CO_EXECUTOR.
        """

        role_ids = StaffTasksRepo._normalize_role_ids(
            staff_role_ids
        )

        conditions = [
            SchoolMonthPlanItemAssignee.month_item_id
            == SchoolMonthPlanItem.id,

            SchoolMonthPlanItemAssignee.staff_role_id.in_(
                role_ids
            ),
        ]

        if assignment_kinds:
            conditions.append(
                SchoolMonthPlanItemAssignee.assignment_kind.in_(
                    list(assignment_kinds)
                )
            )

        return exists(
            select(1)
            .select_from(SchoolMonthPlanItemAssignee)
            .where(*conditions)
        )

    @staticmethod
    def _task_details_options():
        """
        Пакетная загрузка связей задачи.

        assignees загружаются здесь один раз. Повторно добавлять
        selectinload(SchoolMonthPlanItem.assignees) в запросы
        не требуется.
        """

        return (
            joinedload(
                SchoolMonthPlanItem.month_plan
            ).joinedload(
                SchoolMonthPlan.school_plan
            ),

            joinedload(
                SchoolMonthPlanItem.source_row11
            ).selectinload(SchoolPlanRow11.review_places),

            joinedload(SchoolMonthPlanItem.execution),

            selectinload(
                SchoolMonthPlanItem.review_places
            ),

            selectinload(
                SchoolMonthPlanItem.assignees
            ).joinedload(
                SchoolMonthPlanItemAssignee.staff_role
            ).joinedload(
                SchoolStaffRole.staff_member
            ),
        )

    @classmethod
    async def list_tasks_for_staff(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        staff_role_ids: list[int],
        month: int,
        statuses: list[PlanItemStatus] | None = None,
    ) -> list[SchoolMonthPlanItem]:
        """
        Получить задачи сотрудника за выбранный месяц активного годового плана.

        Возвращает задачи, где сотрудник назначен:

        - ответственным — AssignmentKind.PRIMARY;
        - соисполнителем — AssignmentKind.CO_EXECUTOR.

        Разделение на две коллекции выполняется сервисом по
        SchoolMonthPlanItemAssignee.assignment_kind.
        """

        role_ids = cls._normalize_role_ids(
            staff_role_ids
        )

        if not role_ids:
            return []

        status_order = case(
            (
                SchoolMonthPlanItem.status
                == PlanItemStatus.TODO,
                1,
            ),
            (
                SchoolMonthPlanItem.status
                == PlanItemStatus.IN_PROGRESS,
                2,
            ),
            (
                SchoolMonthPlanItem.status
                == PlanItemStatus.DONE,
                3,
            ),
            (
                SchoolMonthPlanItem.status
                == PlanItemStatus.NOT_EXECUTED,
                4,
            ),
            (
                SchoolMonthPlanItem.status
                == PlanItemStatus.REVIEWED,
                5,
            ),
            else_=99,
        )

        staff_assignee_exists = cls._staff_assignee_exists(
            role_ids
        )

        stmt = (
            select(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id
                == SchoolMonthPlan.school_plan_id,
            )
            .where(
                SchoolPlan.school_id == school_id,
                SchoolPlan.status == PlanStatus.ACTIVE.value,
                SchoolMonthPlan.month == month,
                SchoolMonthPlanItem.is_included.is_(True),
                staff_assignee_exists,
            )
            .options(
                raiseload("*"),
                selectinload(SchoolMonthPlanItem.execution_data),
                *cls._task_details_options()
            )
            .order_by(
                SchoolMonthPlanItem.week_of_month
                .asc()
                .nulls_last(),

                SchoolMonthPlanItem.planned_start
                .asc()
                .nulls_last(),

                status_order.asc(),

                SchoolMonthPlanItem.id.asc(),
            )
        )

        if statuses:
            stmt = stmt.where(
                SchoolMonthPlanItem.status.in_(
                    statuses
                )
            )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    @classmethod
    async def get_task_for_staff_status_update(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        staff_role_ids: list[int],
        month_item_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить задачу для изменения общего статуса.

        Изменять общий статус и принимать задачу в исполнение
        может только сотрудник с назначением PRIMARY.
        """

        role_ids = cls._normalize_role_ids(
            staff_role_ids
        )

        if not role_ids:
            return None

        primary_assignee_exists = cls._staff_assignee_exists(
            role_ids,
            assignment_kinds=[
                AssignmentKind.PRIMARY
            ],
        )

        stmt = (
            select(SchoolMonthPlanItem)
            .options(raiseload("*"))
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id
                == SchoolMonthPlan.school_plan_id,
            )
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItem.is_included.is_(True),
                primary_assignee_exists,
            )
        )

        result = await db.execute(stmt)

        return result.scalars().unique().one_or_none()

    @classmethod
    async def get_task_for_execution(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        staff_role_ids: list[int],
        month_item_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить одну задачу для основной страницы исполнения.

        Основной сценарий выполнения общей задачи доступен
        только ответственному исполнителю PRIMARY.

        Соисполнители отображаются в отдельной коллекции и позже
        могут получить собственный сценарий исполнения.
        """

        role_ids = cls._normalize_role_ids(
            staff_role_ids
        )

        if not role_ids:
            return None

        primary_assignee_exists = cls._staff_assignee_exists(
            role_ids,
            assignment_kinds=[
                AssignmentKind.PRIMARY
            ],
        )

        stmt = (
            select(SchoolMonthPlanItem)
            .options(
                # Do not traverse default eager relationships beyond this task.
                raiseload("*"),
                *cls._task_details_options()
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id
                == SchoolMonthPlan.school_plan_id,
            )
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItem.is_included.is_(True),
                primary_assignee_exists,
            )
        )

        result = await db.execute(stmt)

        return result.scalars().unique().one_or_none()
