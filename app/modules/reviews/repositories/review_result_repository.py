# app/modules/reviews/repositories/review_result_repository.py

from __future__ import annotations

from typing import Any

from sqlalchemy import Select, case, func, or_, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, raiseload

from app.modules.planning.enums import (
    PlanItemStatus,
    PlanStatus,
    ReviewPlace,
)
from app.modules.planning.models_month_plan import (
    SchoolMonthPlan,
    SchoolMonthPlanItem,
    SchoolMonthPlanItemAssignee,
    SchoolMonthPlanItemReviewPlace,
)
from app.modules.planning.models_school import (
    SchoolPlan,
)
from app.modules.users.models import User
from app.modules.reports.enums import DocumentType
from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.staff.models_staff_school import (
    SchoolStaffRole, SchoolStaffMember,
)
from app.modules.reviews.models_task_review import (
    SchoolMonthPlanItemReviewResult, SchoolTaskReview,
)


class ReviewResultRepository:
    """
    Репозиторий страницы просмотра результатов рассмотрения задач.

    Ответственность:

    - получение активного годового плана;
    - получение доступных годов и месяцев;
    - выборка задач по инстанции рассмотрения;
    - фильтрация рассмотренных и нерассмотренных задач;
    - ограничение доступа сотрудника;
    - получение задачи с историей рассмотрения;
    - получение конкретного результата;
    - получение истории результатов.

    Репозиторий не определяет роль пользователя и не формирует DTO.
    Эти операции относятся к сервисному слою.
    """

    # ==========================================================
    # 1. Условия доступа
    # ==========================================================

    @staticmethod
    def _assignee_exists_condition(
        *,
        staff_member_id: int,
    ):
        """
        Проверяет, назначен ли сотрудник исполнителем задачи.

        Связь:

        SchoolMonthPlanItem
            -> SchoolMonthPlanItemAssignee
            -> SchoolStaffRole
            -> SchoolStaffMember

        AssignmentKind отдельно проверять не требуется, поскольку
        таблица назначений содержит только PRIMARY и CO_EXECUTOR.
        """

        return (
            select(SchoolMonthPlanItemAssignee.id)
            .join(
                SchoolStaffRole,
                SchoolStaffRole.id
                == SchoolMonthPlanItemAssignee.staff_role_id,
            )
            .where(
                SchoolMonthPlanItemAssignee.month_item_id
                == SchoolMonthPlanItem.id,
                SchoolStaffRole.staff_member_id
                == staff_member_id,
            )
            .correlate(SchoolMonthPlanItem)
            .exists()
        )

    @classmethod
    def _apply_participant_filter(
        cls,
        stmt: Select[Any],
        *,
        participant_user_id: int | None,
        participant_staff_id: int | None,
    ) -> Select[Any]:
        """
        Ограничивает выборку задачами текущего сотрудника.

        Сотрудник считается участником, если:

        1. Он назначен ответственным пользователем:

           SchoolMonthPlanItem.responsible_user_id == user.id

        2. Он назначен основным или дополнительным исполнителем:

           SchoolMonthPlanItemAssignee
               -> SchoolStaffRole
               -> staff_member_id

        Если оба параметра равны None, фильтр не применяется.
        Это режим школьного администратора.
        """

        conditions = []

        if participant_user_id is not None:
            conditions.append(
                SchoolMonthPlanItem.responsible_user_id
                == participant_user_id
            )

        if participant_staff_id is not None:
            conditions.append(
                cls._assignee_exists_condition(
                    staff_member_id=participant_staff_id,
                )
            )

        if not conditions:
            return stmt

        return stmt.where(
            or_(*conditions)
        )

    # ==========================================================
    # 2. Условия рассмотрения
    # ==========================================================

    @staticmethod
    def _review_result_exists_condition(
        *,
        review_place: ReviewPlace,
    ):
        """
        Проверяет наличие результата рассмотрения задачи
        именно в выбранной инстанции.

        Нельзя использовать просто:

            SchoolMonthPlanItem.review_results.any()

        потому что задача может быть рассмотрена в одной инстанции,
        но ещё не рассмотрена в другой.
        """

        return (
            select(SchoolMonthPlanItemReviewResult.id)
            .where(
                SchoolMonthPlanItemReviewResult.month_item_id
                == SchoolMonthPlanItem.id,
                SchoolMonthPlanItemReviewResult.review_place
                == review_place,
            )
            .correlate(SchoolMonthPlanItem)
            .exists()
        )

    @classmethod
    def _apply_reviewed_filter(
        cls,
        stmt: Select[Any],
        *,
        review_place: ReviewPlace,
        reviewed: bool | None,
    ) -> Select[Any]:
        """
        Применяет фильтр по наличию результата рассмотрения.

        reviewed=None:
            все задачи;

        reviewed=True:
            только рассмотренные в выбранной инстанции;

        reviewed=False:
            только нерассмотренные в выбранной инстанции.
        """

        if reviewed is None:
            return stmt

        review_exists = cls._review_result_exists_condition(
            review_place=review_place,
        )

        if reviewed:
            return stmt.where(review_exists)

        return stmt.where(~review_exists)

    # ==========================================================
    # 3. Стандартные eager-load options
    # ==========================================================

    @staticmethod
    def _task_list_options() -> tuple:
        """
        Relationships, необходимые для построения строки списка.

        Документы выполнения и документы протоколов здесь
        не загружаются. Они получаются отдельными SQL-запросами.
        """

        review_results_option = selectinload(
            SchoolMonthPlanItem.review_results
        )

        return (
            selectinload(
                SchoolMonthPlanItem.month_plan
            ),

            selectinload(
                SchoolMonthPlanItem.source_row11
            ),

            selectinload(
                SchoolMonthPlanItem.responsible_user
            ).joinedload(User.staff_member),

            selectinload(
                SchoolMonthPlanItem.review_places
            ),

            selectinload(
                SchoolMonthPlanItem.assignees
            )
            .selectinload(
                SchoolMonthPlanItemAssignee.staff_role
            )
            .selectinload(
                SchoolStaffRole.staff_member
            )
            .selectinload(
                SchoolStaffMember.user_account
            ),

            review_results_option.selectinload(
                SchoolMonthPlanItemReviewResult.task_review
            ),

            review_results_option.selectinload(
                SchoolMonthPlanItemReviewResult.reviewed_by_user
            ).joinedload(User.staff_member),
        )

    @staticmethod
    def _task_detail_options() -> tuple:
        """
        Relationships, необходимые для детальной страницы задачи.

        Документы выполнения загружаются отдельным методом
        get_current_task_documents().
        """

        return (
            *ReviewResultRepository._task_list_options(),

            selectinload(
                SchoolMonthPlanItem.execution
            ),

            selectinload(
                SchoolMonthPlanItem.execution_data
            ),

            selectinload(
                SchoolMonthPlanItem.completed_by
            ),
        )

    @staticmethod
    def _review_result_options() -> tuple:
        """
        Relationships для одного результата рассмотрения.

        Документ протокола загружается отдельным запросом
        get_protocol_documents_by_ids().
        """

        return (
            selectinload(
                SchoolMonthPlanItemReviewResult.task_review
            ),

            selectinload(
                SchoolMonthPlanItemReviewResult.reviewed_by_user
            ).joinedload(User.staff_member),

            selectinload(
                SchoolMonthPlanItemReviewResult.month_item
            ).selectinload(
                SchoolMonthPlanItem.month_plan
            ),

            selectinload(
                SchoolMonthPlanItemReviewResult.month_item
            ).selectinload(
                SchoolMonthPlanItem.source_row11
            ),

            selectinload(
                SchoolMonthPlanItemReviewResult.month_item
            ).selectinload(
                SchoolMonthPlanItem.responsible_user
            ).joinedload(User.staff_member),

            selectinload(
                SchoolMonthPlanItemReviewResult.month_item
            ).selectinload(
                SchoolMonthPlanItem.assignees
            ).selectinload(
                SchoolMonthPlanItemAssignee.staff_role
            ).selectinload(
                SchoolStaffRole.staff_member
            ).selectinload(
                SchoolStaffMember.user_account
            ),
        )

    # ==========================================================
    # 4. Активный годовой план
    # ==========================================================

    @staticmethod
    async def get_active_school_plan(
        db: AsyncSession,
        *,
        school_id: int,
    ) -> SchoolPlan | None:
        """
        Возвращает активный годовой план выбранной школы.

        Если по ошибке найдено несколько активных планов,
        возвращается последний созданный.
        """

        stmt = (
            select(SchoolPlan)
            .options(raiseload("*"))
            .where(
                SchoolPlan.school_id == school_id,
                SchoolPlan.status == PlanStatus.ACTIVE,
            )
            .order_by(
                SchoolPlan.created_at.desc(),
                SchoolPlan.id.desc(),
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # ==========================================================
    # 5. Доступные годы
    # ==========================================================

    @staticmethod
    async def get_available_years(
        db: AsyncSession,
        *,
        school_plan_id: int,
    ) -> list[int]:
        """
        Возвращает календарные годы, для которых существуют
        месячные планы выбранного годового плана.
        """

        stmt = (
            select(SchoolMonthPlan.year)
            .where(
                SchoolMonthPlan.school_plan_id
                == school_plan_id,
            )
            .distinct()
            .order_by(
                SchoolMonthPlan.year.desc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # 6. Доступные месяцы
    # ==========================================================

    @staticmethod
    async def get_available_months(
            db: AsyncSession,
            *,
            school_plan_id: int,
            year: int,
    ) -> list[int]:
        """
        Возвращает доступные месяцы учебного года
        в порядке: сентябрь–декабрь, январь–май.
        """

        month_order = case(
            (
                SchoolMonthPlan.month >= 9,
                SchoolMonthPlan.month - 8,
            ),
            else_=SchoolMonthPlan.month + 4,
        )

        stmt = (
            select(SchoolMonthPlan.month)
            .where(
                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlan.year == year,
            )
            .order_by(month_order)
        )

        result = await db.scalars(stmt)

        return list(result.all())

    # ==========================================================
    # 7. Основной список задач
    # ==========================================================

    @classmethod
    async def get_available_tasks(
        cls,
        db: AsyncSession,
        *,
        school_plan_id: int,
        year: int,
        review_place: ReviewPlace,
        month: int | None = None,
        reviewed: bool | None = None,
        task_review_id: int | None = None,
        participant_user_id: int | None = None,
        participant_staff_id: int | None = None,
    ) -> list[SchoolMonthPlanItem]:
        """
        Возвращает задачи для страницы просмотра результатов.

        Обязательные ограничения:

        - задача относится к выбранному годовому плану;
        - задача относится к выбранному календарному году;
        - задача включена в месячный план;
        - задача назначена выбранной инстанции рассмотрения;
        - задача завершена или отмечена как неисполненная.

        Дополнительные фильтры:

        month:
            конкретный месяц или все месяцы;

        reviewed:
            None  — все;
            True  — рассмотренные;
            False — нерассмотренные;

        participant_user_id / participant_staff_id:
            None / None — администратор видит все задачи;
            значения   — сотрудник видит только свои задачи.
        """

        stmt = (
            select(SchoolMonthPlanItem)
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(
                SchoolMonthPlanItemReviewPlace,
                SchoolMonthPlanItemReviewPlace.month_item_id
                == SchoolMonthPlanItem.id,
            )
            .where(
                SchoolMonthPlan.school_plan_id
                == school_plan_id,

                SchoolMonthPlan.year
                == year,

                SchoolMonthPlanItem.is_included.is_(True),

                SchoolMonthPlanItemReviewPlace.review_place
                == review_place,

                SchoolMonthPlanItem.status.in_(
                    (
                        PlanItemStatus.DONE,
                        PlanItemStatus.NOT_EXECUTED,
                    )
                ),
            )
            .options(
                raiseload("*"),
                *cls._task_list_options()
            )
        )

        if month is not None:
            stmt = stmt.where(
                SchoolMonthPlan.month == month
            )

        stmt = cls._apply_reviewed_filter(
            stmt,
            review_place=review_place,
            reviewed=reviewed,
        )

        stmt = cls._apply_participant_filter(
            stmt,
            participant_user_id=participant_user_id,
            participant_staff_id=participant_staff_id,
        )

        stmt = stmt.order_by(
            SchoolMonthPlan.year.asc(),
            SchoolMonthPlan.month.asc(),
            SchoolMonthPlanItem.planned_start.asc().nulls_last(),
            SchoolMonthPlanItem.planned_end.asc().nulls_last(),
            SchoolMonthPlanItem.id.asc(),
        )

        if task_review_id is not None:
            stmt = stmt.where(
                SchoolMonthPlanItem.review_results.any(
                    and_(
                        SchoolMonthPlanItemReviewResult.task_review_id
                        == task_review_id,

                        SchoolMonthPlanItemReviewResult.review_place
                        == review_place,
                    )
                )
            )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    # ==========================================================
    # 8. Получение одной задачи
    # ==========================================================

    @classmethod
    async def get_task_with_review_history(
            cls,
            db: AsyncSession,
            *,
            month_item_id: int,
            school_id: int,
            review_place: ReviewPlace | None = None,
            participant_user_id: int | None = None,
            participant_staff_id: int | None = None,
    ) -> SchoolMonthPlanItem | None:
        """
        Возвращает задачу вместе с историей рассмотрений.

        Проверяет:

        - принадлежность задачи выбранной школе;
        - включение задачи в месячный план;
        - принадлежность выбранной инстанции, если она передана;
        - право сотрудника на просмотр задачи.

        Статус годового плана не учитывается, поэтому можно просматривать
        историю задач как активного, так и завершённых годовых планов.
        """

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
                SchoolMonthPlanItem.id
                == month_item_id,

                SchoolPlan.school_id
                == school_id,

                SchoolMonthPlanItem.is_included.is_(True),
            )
            .options(
                raiseload("*"),
                *cls._task_detail_options()
            )
        )

        if review_place is not None:
            stmt = stmt.where(
                or_(
                    SchoolMonthPlanItem.review_places.any(SchoolMonthPlanItemReviewPlace.review_place == review_place),
                    SchoolMonthPlanItem.review_results.any(SchoolMonthPlanItemReviewResult.review_place == review_place),
                )
            )

        stmt = cls._apply_participant_filter(
            stmt,
            participant_user_id=participant_user_id,
            participant_staff_id=participant_staff_id,
        )

        result = await db.execute(
            stmt.limit(1)
        )

        return result.scalars().unique().one_or_none()

    # ==========================================================
    # 9. Получение конкретного результата
    # ==========================================================

    @classmethod
    async def get_result_by_id(
        cls,
        db: AsyncSession,
        *,
        review_result_id: int,
        school_plan_id: int | None = None,
        school_id: int | None = None,
        participant_user_id: int | None = None,
        participant_staff_id: int | None = None,
    ) -> SchoolMonthPlanItemReviewResult | None:
        """
        Возвращает конкретный результат рассмотрения.

        Проверяет:

        - существование результата;
        - принадлежность задачи годовому плану;
        - доступ сотрудника к задаче.
        """

        if school_plan_id is None and school_id is None:
            raise ValueError("Не указана область доступа к результату.")

        stmt = (
            select(SchoolMonthPlanItemReviewResult)
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemReviewResult.month_item_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .join(SchoolPlan, SchoolPlan.id == SchoolMonthPlan.school_plan_id)
            .where(
                SchoolMonthPlanItemReviewResult.id
                == review_result_id,

                SchoolMonthPlanItem.is_included.is_(True),
            )
            .options(
                raiseload("*"),
                *cls._review_result_options()
            )
        )

        if school_plan_id is not None:
            stmt = stmt.where(SchoolMonthPlan.school_plan_id == school_plan_id)
        if school_id is not None:
            stmt = stmt.where(SchoolPlan.school_id == school_id)

        stmt = cls._apply_participant_filter(
            stmt,
            participant_user_id=participant_user_id,
            participant_staff_id=participant_staff_id,
        )

        result = await db.execute(
            stmt.limit(1)
        )

        return result.scalars().unique().one_or_none()

    # ==========================================================
    # 10. История рассмотрений задачи
    # ==========================================================

    @classmethod
    async def get_history_by_month_item_id(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        school_plan_id: int,
        review_place: ReviewPlace | None = None,
        participant_user_id: int | None = None,
        participant_staff_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SchoolMonthPlanItemReviewResult]:
        """
        Возвращает историю рассмотрений выбранной задачи.

        review_place=None:
            вся история задачи;

        review_place указан:
            история только выбранной инстанции.
        """

        if limit < 1:
            raise ValueError(
                "limit должен быть больше нуля."
            )

        if limit > 200:
            raise ValueError(
                "limit не должен превышать 200."
            )

        if offset < 0:
            raise ValueError(
                "offset не может быть отрицательным."
            )

        stmt = (
            select(SchoolMonthPlanItemReviewResult)
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemReviewResult.month_item_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .where(
                SchoolMonthPlanItemReviewResult.month_item_id
                == month_item_id,

                SchoolMonthPlan.school_plan_id
                == school_plan_id,

                SchoolMonthPlanItem.is_included.is_(True),
            )
            .options(
                raiseload("*"),
                *cls._review_result_options()
            )
        )

        if review_place is not None:
            stmt = stmt.where(
                SchoolMonthPlanItemReviewResult.review_place
                == review_place
            )

        stmt = cls._apply_participant_filter(
            stmt,
            participant_user_id=participant_user_id,
            participant_staff_id=participant_staff_id,
        )

        stmt = (
            stmt
            .order_by(
                SchoolMonthPlanItemReviewResult.reviewed_at
                .desc()
                .nulls_last(),

                SchoolMonthPlanItemReviewResult.created_at.desc(),

                SchoolMonthPlanItemReviewResult.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    # ==========================================================
    # 11. Количество результатов задачи
    # ==========================================================

    @classmethod
    async def count_by_month_item_id(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        school_plan_id: int,
        review_place: ReviewPlace | None = None,
        participant_user_id: int | None = None,
        participant_staff_id: int | None = None,
    ) -> int:
        """
        Возвращает количество результатов рассмотрения задачи.

        Проверка доступа выполняется в том же SQL-запросе.
        """

        stmt = (
            select(
                func.count(
                    SchoolMonthPlanItemReviewResult.id
                )
            )
            .select_from(
                SchoolMonthPlanItemReviewResult
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemReviewResult.month_item_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .where(
                SchoolMonthPlanItemReviewResult.month_item_id
                == month_item_id,

                SchoolMonthPlan.school_plan_id
                == school_plan_id,

                SchoolMonthPlanItem.is_included.is_(True),
            )
        )

        if review_place is not None:
            stmt = stmt.where(
                SchoolMonthPlanItemReviewResult.review_place
                == review_place
            )

        stmt = cls._apply_participant_filter(
            stmt,
            participant_user_id=participant_user_id,
            participant_staff_id=participant_staff_id,
        )

        result = await db.execute(stmt)

        return int(
            result.scalar_one() or 0
        )

    # ==========================================================
    # 12. Проверка наличия результата
    # ==========================================================

    @classmethod
    async def exists_for_month_item_id(
        cls,
        db: AsyncSession,
        *,
        month_item_id: int,
        school_plan_id: int,
        review_place: ReviewPlace | None = None,
        participant_user_id: int | None = None,
        participant_staff_id: int | None = None,
    ) -> bool:
        """
        Проверяет наличие хотя бы одного результата рассмотрения.

        Если указана review_place, проверяется наличие результата
        именно в выбранной инстанции.
        """

        stmt = (
            select(
                SchoolMonthPlanItemReviewResult.id
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemReviewResult.month_item_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .where(
                SchoolMonthPlanItemReviewResult.month_item_id
                == month_item_id,

                SchoolMonthPlan.school_plan_id
                == school_plan_id,

                SchoolMonthPlanItem.is_included.is_(True),
            )
        )

        if review_place is not None:
            stmt = stmt.where(
                SchoolMonthPlanItemReviewResult.review_place
                == review_place
            )

        stmt = cls._apply_participant_filter(
            stmt,
            participant_user_id=participant_user_id,
            participant_staff_id=participant_staff_id,
        )

        result = await db.execute(
            stmt.limit(1)
        )

        return result.scalar_one_or_none() is not None

    @classmethod
    async def get_available_protocols(
            cls,
            db: AsyncSession,
            *,
            school_plan_id: int,
            year: int,
            review_place: ReviewPlace,
            month: int | None = None,
            participant_user_id: int | None = None,
            participant_staff_id: int | None = None,
    ) -> list[SchoolTaskReview]:
        """
        Возвращает протоколы, по которым имеются результаты
        рассмотрения задач выбранного плана, года и инстанции.
        """

        stmt = (
            select(SchoolTaskReview)
            .join(
                SchoolMonthPlanItemReviewResult,
                SchoolMonthPlanItemReviewResult.task_review_id
                == SchoolTaskReview.id,
            )
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == SchoolMonthPlanItemReviewResult.month_item_id,
            )
            .join(
                SchoolMonthPlan,
                SchoolMonthPlan.id
                == SchoolMonthPlanItem.month_plan_id,
            )
            .where(
                SchoolTaskReview.school_plan_id == school_plan_id,
                SchoolTaskReview.review_place == review_place,

                SchoolMonthPlan.school_plan_id == school_plan_id,
                SchoolMonthPlan.year == year,

                SchoolMonthPlanItem.is_included.is_(True),

                SchoolMonthPlanItemReviewResult.review_place
                == review_place,
            )
        )

        stmt = cls._apply_participant_filter(
            stmt, participant_user_id=participant_user_id, participant_staff_id=participant_staff_id,
        )
        if month is not None:
            stmt = stmt.where(
                SchoolMonthPlan.month == month
            )

        stmt = (
            stmt
            .distinct()
            .order_by(
                SchoolTaskReview.protocol_date.desc(),
                SchoolTaskReview.protocol_number.desc(),
                SchoolTaskReview.id.desc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().unique().all()
        )

    @staticmethod
    async def get_current_task_documents(
            db: AsyncSession,
            *,
            month_item_id: int,
    ) -> list[TaskExecutionDocument]:
        """
        Возвращает актуальные сформированные документы выполнения задачи.

        В выборку входят:
        - итоговый документ;
        - отправленные отчеты исполнителей.

        Черновики и документы без файла не возвращаются.
        """

        stmt = (
            select(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.month_item_id == month_item_id,
                TaskExecutionDocument.is_current.is_(True),
                TaskExecutionDocument.document_type
                != DocumentType.PROTOCOL,
                TaskExecutionDocument.file_path.is_not(None),
                TaskExecutionDocument.file_path != "",
            )
            .order_by(
                TaskExecutionDocument.is_final.desc(),
                TaskExecutionDocument.submitted_at.asc().nulls_last(),
                TaskExecutionDocument.created_at.asc(),
                TaskExecutionDocument.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_protocol_documents_by_ids(
            db: AsyncSession,
            *,
            document_ids: list[int],
    ) -> dict[int, TaskExecutionDocument]:
        """
        Возвращает документы протоколов по идентификаторам.

        Ключ словаря — идентификатор документа.
        """

        unique_document_ids = list(
            dict.fromkeys(document_ids)
        )

        if not unique_document_ids:
            return {}

        stmt = (
            select(TaskExecutionDocument)
            .where(
                TaskExecutionDocument.id.in_(
                    unique_document_ids
                ),
                TaskExecutionDocument.document_type
                == DocumentType.PROTOCOL,
                TaskExecutionDocument.file_path.is_not(None),
                TaskExecutionDocument.file_path != "",
            )
        )

        result = await db.execute(stmt)

        documents = result.scalars().all()

        return {
            document.id: document
            for document in documents
        }

    @classmethod
    async def get_document_for_access(
            cls,
            db: AsyncSession,
            *,
            document_id: int,
            school_id: int,
            participant_user_id: int | None = None,
            participant_staff_id: int | None = None,
    ) -> TaskExecutionDocument | None:
        """
        Возвращает документ, если связанная задача принадлежит школе
        и доступна текущему пользователю.
        """

        stmt = (
            select(TaskExecutionDocument)
            .join(
                SchoolMonthPlanItem,
                SchoolMonthPlanItem.id
                == TaskExecutionDocument.month_item_id,
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
                TaskExecutionDocument.id == document_id,
                SchoolPlan.school_id == school_id,
                SchoolMonthPlanItem.is_included.is_(True),
                TaskExecutionDocument.file_path.is_not(None),
                TaskExecutionDocument.file_path != "",
            )
        )

        stmt = cls._apply_participant_filter(
            stmt,
            participant_user_id=participant_user_id,
            participant_staff_id=participant_staff_id,
        )

        result = await db.execute(
            stmt.limit(1)
        )

        return result.scalars().unique().one_or_none()
