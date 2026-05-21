from sqlalchemy import String, case, cast as sa_cast, exists, func, select, literal
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.modules.planning.enums import PlanItemStatus
from app.modules.planning.models_month_plan import (
    SchoolMonthPlanItem,
    SchoolMonthPlan, SchoolMonthPlanItemReviewPlace,
)
from app.modules.planning.models_month_plan import SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import SchoolPlan, SchoolPlanRow11
from app.modules.reports.models_documents import TaskExecutionSelectedReport, TaskExecutionData
from app.modules.tasks.schemas import MyTaskRow


class StaffTasksRepo:
    @staticmethod
    async def list_tasks_for_staff(
            db: AsyncSession,
            *,
            school_id: int,
            staff_role_ids: list[int],
            month: int,
            statuses: list[PlanItemStatus] | None = None,
    ) -> list[MyTaskRow]:
        """
        Быстрая выборка задач сотрудника для страницы списка.
        """

        if not staff_role_ids:
            return []

        status_order = case(
            (SchoolMonthPlanItem.status == PlanItemStatus.TODO, 1),
            (SchoolMonthPlanItem.status == PlanItemStatus.IN_PROGRESS, 2),
            (SchoolMonthPlanItem.status == PlanItemStatus.DONE, 3),
            (SchoolMonthPlanItem.status == PlanItemStatus.NOT_EXECUTED, 4),
            else_=99,
        )

        assignee_exists = exists(
            select(1).where(
                SchoolMonthPlanItemAssignee.month_item_id == SchoolMonthPlanItem.id,
                SchoolMonthPlanItemAssignee.staff_role_id.in_(staff_role_ids),
            )
        )

        selected_reports_exists = exists(
            select(1)
            .select_from(TaskExecutionSelectedReport)
            .join(
                TaskExecutionData,
                TaskExecutionData.id == TaskExecutionSelectedReport.execution_data_id,
            )
            .where(
                TaskExecutionData.month_item_id == SchoolMonthPlanItem.id,
            )
        )

        review_place_text = sa_cast(
            SchoolMonthPlanItemReviewPlace.review_place,
            String,
        )

        review_place_agg = func.coalesce(
            func.string_agg(
                review_place_text,
                aggregate_order_by(literal(", "), review_place_text),
            ),
            "—",
        ).label("review_place")

        stmt = (
            select(
                SchoolMonthPlanItem.id.label("month_item_id"),
                SchoolMonthPlanItem.week_of_month.label("week_of_month"),
                SchoolMonthPlanItem.planned_start.label("planned_start"),
                SchoolMonthPlanItem.planned_end.label("planned_end"),
                SchoolPlanRow11.topic.label("topic"),
                SchoolPlanRow11.goal.label("goal"),
                SchoolPlanRow11.control_object.label("control_object"),
                SchoolPlanRow11.control_type.label("control_type"),
                SchoolMonthPlanItem.status.label("status"),
                selected_reports_exists.label("has_selected_reports"),
                review_place_agg,
            )
            .select_from(SchoolMonthPlanItem)
            .outerjoin(
                SchoolPlanRow11,
                SchoolPlanRow11.id == SchoolMonthPlanItem.source_row11_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id == SchoolMonthPlan.school_plan_id,
            )
            .outerjoin(
                SchoolMonthPlanItemReviewPlace,
                SchoolMonthPlanItemReviewPlace.month_item_id == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolPlan.school_id == school_id,
                SchoolMonthPlan.month == month,
                SchoolMonthPlanItem.is_included.is_(True),
                assignee_exists,
            )
            .group_by(
                SchoolMonthPlanItem.id,
                SchoolMonthPlanItem.week_of_month,
                SchoolMonthPlanItem.planned_start,
                SchoolMonthPlanItem.planned_end,
                SchoolMonthPlanItem.status,
                SchoolPlanRow11.topic,
                SchoolPlanRow11.goal,
                SchoolPlanRow11.control_object,
                SchoolPlanRow11.control_type,
            )
            .order_by(
                SchoolMonthPlanItem.week_of_month.asc().nulls_last(),
                SchoolMonthPlanItem.planned_start.asc().nulls_last(),
                status_order.asc(),
                SchoolMonthPlanItem.id.asc(),
            )
        )

        if statuses:
            stmt = stmt.where(SchoolMonthPlanItem.status.in_(statuses))

        result = await db.execute(stmt)
        rows = result.mappings().all()

        return [
            MyTaskRow(
                month_item_id=row["month_item_id"],
                week_of_month=row["week_of_month"],
                planned_start=row["planned_start"],
                planned_end=row["planned_end"],
                topic=row["topic"],
                goal=row["goal"],
                control_object=row["control_object"],
                control_type=row["control_type"],
                review_place=row["review_place"],
                status=row["status"],
                has_selected_reports=bool(row["has_selected_reports"]),
            )
            for row in rows
        ]

    @staticmethod
    async def get_task_for_staff_status_update(
            db: AsyncSession,
            *,
            school_id: int,
            staff_role_ids: list[int],
            month_item_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить задачу сотрудника для смены статуса.

        Для чего нужен:
        - используется в сервисе take_task_to_work()
        - проверяет, что задача принадлежит школе пользователя
        - проверяет, что задача назначена хотя бы на одну активную роль сотрудника
        - возвращает ORM-объект задачи для безопасного обновления статуса

        Почему метод находится в StaffTasksRepo:
        - это часть staff-domain
        - здесь решается вопрос доступа сотрудника к задаче
        - здесь же удобно централизовать проверку назначения через EXISTS

        Почему такой запрос оптимален:
        - не делает лишних joinedload/selectinload
        - не тащит тяжелые связанные сущности
        - использует EXISTS вместо join к assignees, чтобы не дублировать строки
        - возвращает только одну задачу, достаточную для update статуса
        """
        if not staff_role_ids:
            return None

        assignee_exists = exists(
            select(1).where(
                SchoolMonthPlanItemAssignee.month_item_id == SchoolMonthPlanItem.id,
                SchoolMonthPlanItemAssignee.staff_role_id.in_(staff_role_ids),
            )
        )

        stmt = (
            select(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id == SchoolMonthPlan.school_plan_id,
            )
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItem.is_included.is_(True),
                assignee_exists,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_task_for_execution(
            db: AsyncSession,
            *,
            school_id: int,
            staff_role_ids: list[int],
            month_item_id: int,
    ) -> SchoolMonthPlanItem | None:
        """
        Получить задачу для страницы исполнения с проверкой доступа сотрудника.

        Для чего нужен:
        - используется в сервисе get_execution_page_payload()
        - загружает только одну выбранную задачу
        - проверяет доступ сотрудника к этой задаче
        - подгружает только те связи, которые реально нужны на task_execute.html

        Какие данные должны быть доступны после запроса:
        - month_plan -> school_plan -> school_id
        - source_row11
        - review_places

        Важно:
        - review_place внутри SchoolMonthPlanItemReviewPlace является обычным полем,
          а не relationship, поэтому дополнительный selectinload для него не нужен

        Почему метод находится в StaffTasksRepo:
        - доступ к задаче и принадлежность задачи сотруднику — это staff-domain
        - даже если экран относится к reports, граница доступа должна проверяться здесь

        Почему такой запрос оптимален:
        - грузит только одну задачу
        - использует EXISTS, чтобы не дублировать строки по assignees
        - использует ограниченный набор eager loading только для реально нужных связей
        - не строит DTO на уровне repo, а только возвращает модель для сервисного слоя
        """
        if not staff_role_ids:
            return None

        assignee_exists = exists(
            select(1).where(
                SchoolMonthPlanItemAssignee.month_item_id == SchoolMonthPlanItem.id,
                SchoolMonthPlanItemAssignee.staff_role_id.in_(staff_role_ids),
            )
        )

        stmt = (
            select(SchoolMonthPlanItem)
            .options(
                joinedload(SchoolMonthPlanItem.month_plan)
                .joinedload(SchoolMonthPlan.school_plan),
                selectinload(SchoolMonthPlanItem.source_row11),
                selectinload(SchoolMonthPlanItem.review_places),
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlan,
                SchoolPlan.id == SchoolMonthPlan.school_plan_id,
            )
            .where(
                SchoolMonthPlanItem.id == month_item_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItem.is_included.is_(True),
                assignee_exists,
            )
        )

        result = await db.execute(stmt)
        return result.scalars().unique().one_or_none()
