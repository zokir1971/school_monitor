# app/modules/statistics/school_statistic_repo.py

from __future__ import annotations

from sqlalchemy import select, func, case, distinct, exists, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, raiseload

from app.modules.planning.enums import PlanItemStatus, PlanStatus
from app.modules.planning.models import PlanDirection
from app.modules.planning.models_month_plan import SchoolMonthPlan, SchoolMonthPlanItem, SchoolMonthPlanItemAssignee
from app.modules.planning.models_school import (
    SchoolPlan,
    SchoolPlanRow11,
    SchoolPlanRow11ReviewPlace,
)
from app.modules.reviews.models_task_review import SchoolMonthPlanItemReviewResult
from app.modules.staff.models_staff_school import SchoolStaffRole
from app.modules.users.models import User


class SchoolPlanStatisticsRepository:
    """Репозиторий статистики годового плана школы.

    Репозиторий только читает данные из БД и не формирует DTO,
    не рассчитывает проценты, итоги и сравнения.
    """

    @staticmethod
    async def get_active_school_plan(
            db: AsyncSession,
            *,
            school_id: int,
    ) -> SchoolPlan | None:
        stmt = (
            select(SchoolPlan)
            .options(raiseload("*"), joinedload(SchoolPlan.school))
            .where(
                SchoolPlan.school_id == school_id,
                SchoolPlan.status == PlanStatus.ACTIVE,
            )
            .order_by(SchoolPlan.id.desc())
            .limit(1)
        )

        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def get_directions(db: AsyncSession):
        stmt = (
            select(
                PlanDirection.id.label("direction_id"),
                PlanDirection.full_title.label("direction_name"),
            )
            .order_by(PlanDirection.id)
        )

        result = await db.execute(stmt)
        return result.all()

    @staticmethod
    async def get_plan_rows(
            db: AsyncSession,
            *,
            school_plan_id: int,
    ):
        stmt = (
            select(
                SchoolPlanRow11.id.label("row_id"),
                SchoolPlanRow11.direction_id,
                SchoolPlanRow11.row_order,
                SchoolPlanRow11.period_type,
                SchoolPlanRow11.period_value_int,
                SchoolPlanRow11.period_values,
            )
            .where(SchoolPlanRow11.school_plan_id == school_plan_id, SchoolPlanRow11.is_excluded.is_(False))
            .order_by(
                SchoolPlanRow11.direction_id,
                SchoolPlanRow11.row_order,
            )
        )

        result = await db.execute(stmt)
        return result.all()

    @staticmethod
    async def get_review_place_rows(
            db: AsyncSession,
            *,
            school_plan_id: int,
    ):
        stmt = (
            select(
                SchoolPlanRow11.id.label("row_id"),
                SchoolPlanRow11.direction_id,
                SchoolPlanRow11.row_order,
                SchoolPlanRow11ReviewPlace.review_place,
            )
            .join(
                SchoolPlanRow11ReviewPlace,
                SchoolPlanRow11ReviewPlace.row11_id == SchoolPlanRow11.id,
            )
            .where(SchoolPlanRow11.school_plan_id == school_plan_id, SchoolPlanRow11.is_excluded.is_(False))
            .order_by(
                SchoolPlanRow11.direction_id,
                SchoolPlanRow11.row_order,
            )
        )

        result = await db.execute(stmt)
        return result.all()


class SchoolStatisticsRepository:

    @classmethod
    async def get_monthly_execution_counts(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ):
        """
        Возвращает статистику выполнения и рассмотрения
        по каждому созданному месячному плану.

        В статистику включаются только задачи,
        у которых is_included = True.

        Созданный месячный план без задач также
        возвращается со значениями 0.
        """

        reviewed_items_subquery = cls._reviewed_items_subquery()

        stmt = (
            select(
                SchoolMonthPlan.id.label("month_plan_id"),
                SchoolMonthPlan.year,
                SchoolMonthPlan.month,
                SchoolMonthPlan.status.label("plan_status"),

                func.count(
                    SchoolMonthPlanItem.id
                ).label("planned_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.DONE,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("completed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.IN_PROGRESS,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("in_progress_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.NOT_EXECUTED,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("not_executed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.TODO,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("todo_count"),

                func.count(
                    distinct(
                        reviewed_items_subquery.c.month_item_id
                    )
                ).label("reviewed_count"),
            )
            .select_from(SchoolMonthPlan)
            .outerjoin(
                SchoolMonthPlanItem,
                (
                        SchoolMonthPlanItem.month_plan_id
                        == SchoolMonthPlan.id
                )
                & SchoolMonthPlanItem.is_included.is_(True),
            )
            .outerjoin(
                reviewed_items_subquery,
                reviewed_items_subquery.c.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
            )
            .group_by(
                SchoolMonthPlan.id,
                SchoolMonthPlan.year,
                SchoolMonthPlan.month,
                SchoolMonthPlan.status,
            )
            .order_by(
                case(
                    (SchoolMonthPlan.month == 8, 1),
                    (SchoolMonthPlan.month == 9, 2),
                    (SchoolMonthPlan.month == 10, 3),
                    (SchoolMonthPlan.month == 11, 4),
                    (SchoolMonthPlan.month == 12, 5),
                    (SchoolMonthPlan.month == 1, 6),
                    (SchoolMonthPlan.month == 2, 7),
                    (SchoolMonthPlan.month == 3, 8),
                    (SchoolMonthPlan.month == 4, 9),
                    (SchoolMonthPlan.month == 5, 10),
                    (SchoolMonthPlan.month == 6, 11),
                    else_=12,
                )
            )
        )

        result = await db.execute(stmt)
        return result.all()

    @staticmethod
    def _reviewed_items_subquery():
        """
        Возвращает уникальные задачи,
        имеющие завершённый результат рассмотрения.
        """
        return (
            select(
                SchoolMonthPlanItemReviewResult.month_item_id.label(
                    "month_item_id"
                )
            )
            .where(
                SchoolMonthPlanItemReviewResult.reviewed_at.is_not(None),
            )
            .distinct()
            .subquery()
        )

    @classmethod
    async def get_annual_direction_execution_counts(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
    ):
        """
        Возвращает количество месячных задач,
        выполненных и рассмотренных задач
        по направлениям годового плана.
        """

        reviewed_items_subquery = cls._reviewed_items_subquery()

        stmt = (
            select(
                SchoolPlanRow11.direction_id.label("direction_id"),

                func.count(
                    SchoolMonthPlanItem.id
                ).label("included_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.DONE,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("completed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.IN_PROGRESS,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("in_progress_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.NOT_EXECUTED,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("not_executed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.TODO,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("todo_count"),

                func.count(
                    distinct(
                        reviewed_items_subquery.c.month_item_id
                    )
                ).label("reviewed_count"),
            )
            .select_from(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolPlanRow11,
                SchoolPlanRow11.id
                == SchoolMonthPlanItem.source_row11_id,
            )
            .outerjoin(
                reviewed_items_subquery,
                reviewed_items_subquery.c.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlanItem.is_included.is_(True),
                SchoolPlanRow11.direction_id.is_not(None),
            )
            .group_by(
                SchoolPlanRow11.direction_id,
            )
            .order_by(
                SchoolPlanRow11.direction_id,
            )
        )

        result = await db.execute(stmt)
        return result.all()

    @classmethod
    async def get_month_direction_execution_counts(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
    ):
        """
        Возвращает выполнение и рассмотрение задач
        выбранного месячного плана по направлениям.
        """

        reviewed_items_subquery = cls._reviewed_items_subquery()

        stmt = (
            select(
                SchoolPlanRow11.direction_id.label("direction_id"),

                func.count(
                    SchoolMonthPlanItem.id
                ).label("planned_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.DONE,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("completed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.IN_PROGRESS,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("in_progress_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.NOT_EXECUTED,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("not_executed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.TODO,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("todo_count"),

                func.count(
                    distinct(
                        reviewed_items_subquery.c.month_item_id
                    )
                ).label("reviewed_count"),
            )
            .select_from(SchoolMonthPlanItem)
            .join(
                SchoolPlanRow11,
                SchoolPlanRow11.id
                == SchoolMonthPlanItem.source_row11_id,
            )
            .outerjoin(
                reviewed_items_subquery,
                reviewed_items_subquery.c.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlanItem.month_plan_id == month_plan_id,
                SchoolMonthPlanItem.is_included.is_(True),
                SchoolPlanRow11.direction_id.is_not(None),
            )
            .group_by(
                SchoolPlanRow11.direction_id,
            )
            .order_by(
                SchoolPlanRow11.direction_id,
            )
        )

        result = await db.execute(stmt)
        return result.all()


class StaffStatisticsRepository:
    """
    Репозиторий личной статистики сотрудника.

    Учитывает задачи, где сотрудник:
    - основной ответственный;
    - исполнитель;
    - соисполнитель.

    Каждая задача считается только один раз.
    """

    @staticmethod
    def _reviewed_items_subquery():
        """
        Уникальные задачи, которые были рассмотрены.
        """
        return (
            select(
                SchoolMonthPlanItemReviewResult.month_item_id.label(
                    "month_item_id"
                )
            )
            .where(
                SchoolMonthPlanItemReviewResult.reviewed_at.is_not(None),
            )
            .distinct()
            .subquery()
        )

    @staticmethod
    def _staff_task_condition(
            *,
            user_id: int,
    ):
        assignee_exists = exists(
            select(1)
            .select_from(SchoolMonthPlanItemAssignee)
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .join(
                User,
                User.staff_member_id
                == SchoolStaffRole.staff_member_id,
            )
            .where(
                SchoolMonthPlanItemAssignee.month_item_id
                == SchoolMonthPlanItem.id,
                User.id == user_id,
            )
        )

        return or_(
            SchoolMonthPlanItem.responsible_user_id == user_id,
            assignee_exists,
        )

    @classmethod
    async def get_monthly_execution_counts(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            user_id: int,
    ):
        """
        Личная статистика сотрудника
        по каждому созданному месячному плану.
        """

        reviewed_items_subquery = cls._reviewed_items_subquery()

        stmt = (
            select(
                SchoolMonthPlan.id.label("month_plan_id"),
                SchoolMonthPlan.year,
                SchoolMonthPlan.month,
                SchoolMonthPlan.status.label("plan_status"),

                func.count(
                    SchoolMonthPlanItem.id
                ).label("assigned_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.DONE,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("completed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.IN_PROGRESS,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("in_progress_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.NOT_EXECUTED,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("not_executed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.TODO,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("todo_count"),

                func.count(
                    distinct(
                        reviewed_items_subquery.c.month_item_id
                    )
                ).label("reviewed_count"),
            )
            .select_from(SchoolMonthPlan)
            .outerjoin(
                SchoolMonthPlanItem,
                (
                        SchoolMonthPlanItem.month_plan_id
                        == SchoolMonthPlan.id
                )
                & SchoolMonthPlanItem.is_included.is_(True)
                & cls._staff_task_condition(
                    user_id=user_id,
                ),
            )
            .outerjoin(
                reviewed_items_subquery,
                reviewed_items_subquery.c.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
            )
            .group_by(
                SchoolMonthPlan.id,
                SchoolMonthPlan.year,
                SchoolMonthPlan.month,
                SchoolMonthPlan.status,
            )
            .order_by(
                case(
                    (SchoolMonthPlan.month == 8, 1),
                    (SchoolMonthPlan.month == 9, 2),
                    (SchoolMonthPlan.month == 10, 3),
                    (SchoolMonthPlan.month == 11, 4),
                    (SchoolMonthPlan.month == 12, 5),
                    (SchoolMonthPlan.month == 1, 6),
                    (SchoolMonthPlan.month == 2, 7),
                    (SchoolMonthPlan.month == 3, 8),
                    (SchoolMonthPlan.month == 4, 9),
                    (SchoolMonthPlan.month == 5, 10),
                    (SchoolMonthPlan.month == 6, 11),
                    else_=12,
                )
            )
        )

        result = await db.execute(stmt)
        return result.all()

    @classmethod
    async def get_month_direction_execution_counts(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
            user_id: int,
    ):
        """
        Личная статистика сотрудника
        по направлениям выбранного месяца.
        """

        reviewed_items_subquery = cls._reviewed_items_subquery()

        stmt = (
            select(
                SchoolPlanRow11.direction_id.label(
                    "direction_id"
                ),

                func.count(
                    SchoolMonthPlanItem.id
                ).label("assigned_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.DONE,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("completed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.IN_PROGRESS,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("in_progress_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.NOT_EXECUTED,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("not_executed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.TODO,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("todo_count"),

                func.count(
                    distinct(
                        reviewed_items_subquery.c.month_item_id
                    )
                ).label("reviewed_count"),
            )
            .select_from(SchoolMonthPlanItem)
            .join(
                SchoolPlanRow11,
                SchoolPlanRow11.id
                == SchoolMonthPlanItem.source_row11_id,
            )
            .outerjoin(
                reviewed_items_subquery,
                reviewed_items_subquery.c.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlanItem.month_plan_id
                == month_plan_id,
                SchoolMonthPlanItem.is_included.is_(True),
                SchoolPlanRow11.direction_id.is_not(None),
                cls._staff_task_condition(
                    user_id=user_id,
                ),
            )
            .group_by(
                SchoolPlanRow11.direction_id,
            )
            .order_by(
                SchoolPlanRow11.direction_id,
            )
        )

        result = await db.execute(stmt)
        return result.all()

    @classmethod
    async def get_total_execution_counts(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            user_id: int,
    ):
        """
        Общие личные показатели сотрудника
        за выбранный годовой план.
        """

        reviewed_items_subquery = cls._reviewed_items_subquery()

        stmt = (
            select(
                func.count(
                    SchoolMonthPlanItem.id
                ).label("assigned_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.DONE,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("completed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.IN_PROGRESS,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("in_progress_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.NOT_EXECUTED,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("not_executed_count"),

                func.count(
                    case(
                        (
                            SchoolMonthPlanItem.status
                            == PlanItemStatus.TODO,
                            SchoolMonthPlanItem.id,
                        )
                    )
                ).label("todo_count"),

                func.count(
                    distinct(
                        reviewed_items_subquery.c.month_item_id
                    )
                ).label("reviewed_count"),
            )
            .select_from(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .outerjoin(
                reviewed_items_subquery,
                reviewed_items_subquery.c.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlan.school_plan_id
                == school_plan_id,
                SchoolMonthPlanItem.is_included.is_(True),
                cls._staff_task_condition(
                    user_id=user_id,
                ),
            )
        )

        result = await db.execute(stmt)
        return result.one()
