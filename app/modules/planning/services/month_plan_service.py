# app/modules/planning/services/month_plan_service.py
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.constants import (
    ACADEMIC_MONTHS,
)
from app.modules.planning.enums import PlanStatus, PlanPeriodType
from app.modules.planning.repositories.month_plan_repository import (
    SchoolMonthlyPlanRepo,
    SchoolMonthPlanItemRepo,
)
from app.modules.planning.schemas.month_plan_page_schemas import (
    MonthPlanDirectionBlockDTO,
    MonthPlanItemRowDTO,
)
from app.modules.planning.services.month_plan_builder import MonthPlanBuilder
from app.modules.planning.utils.month_plan_utils import month_item_review_place_labels
from app.modules.planning.utils.month_plan_utils import (
    previous_months_in_quarter,
)
from app.utils.calendar_weeks import month_weeks_grid


class SchoolMonthlyPlanningService:
    @classmethod
    async def build_month_plan_direction_blocks(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
    ) -> list[MonthPlanDirectionBlockDTO]:
        """
        Подготовить блоки направлений для страницы месячного плана.

        Выполняются пакетные запросы:

        1. строки месячного плана с исходными строками
           годового плана и направлениями;
        2. краткие сводки назначений с сокращёнными ФИО
           ответственного и соисполнителей.

        ORM-модели сотрудников в шаблон не передаются.
        """

        items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan_id,
            with_source=True,
        )

        assignment_summaries = (
            await SchoolMonthlyPlanRepo
            .get_assignment_summaries_by_month_plan(
                db,
                month_plan_id=month_plan_id,
            )
        )

        blocks_by_direction: dict[
            int,
            MonthPlanDirectionBlockDTO,
        ] = {}

        for item in items:
            source_row = item.source_row11

            direction = (
                source_row.direction
                if source_row is not None
                else None
            )

            direction_id = (
                    getattr(source_row, "direction_id", None)
                    or 0
            )

            direction_name = (
                    getattr(direction, "short_title", None)
                    or getattr(direction, "title", None)
                    or "Без направления"
            )

            direction_sort_order = (
                getattr(direction, "sort_order", None)
                if direction is not None
                else None
            )

            assignment_summary = assignment_summaries.get(
                item.id
            )

            if assignment_summary is None:
                has_primary_assignee = False
                primary_assignee_name = None
                co_executor_count = 0
                co_executor_names: list[str] = []
            else:
                has_primary_assignee = (
                    assignment_summary.has_primary_assignee
                )
                primary_assignee_name = (
                    assignment_summary.primary_assignee_name
                )
                co_executor_count = (
                    assignment_summary.co_executor_count
                )
                co_executor_names = list(
                    assignment_summary.co_executor_names
                )

            row_dto = MonthPlanItemRowDTO(
                id=item.id,
                source_row11_id=item.source_row11_id,

                is_included=bool(item.is_included),
                week_of_month=item.week_of_month,
                planned_start=item.planned_start,
                planned_end=item.planned_end,
                notes=item.notes,

                status=cls._enum_value(item.status),
                status_label=cls._enum_label(item.status),

                topic=(
                        getattr(source_row, "topic", None)
                        or ""
                ),
                goal=(
                        getattr(source_row, "goal", None)
                        or ""
                ),
                control_object=(
                        getattr(source_row, "control_object", None)
                        or ""
                ),
                methods=(
                        getattr(source_row, "methods", None)
                        or ""
                ),
                deadlines=(
                        getattr(source_row, "deadlines", None)
                        or ""
                ),

                period_type=cls._enum_value(
                    getattr(
                        source_row,
                        "period_type",
                        None,
                    )
                ),
                period_value_int=getattr(
                    source_row,
                    "period_value_int",
                    None,
                ),
                period_values=getattr(
                    source_row,
                    "period_values",
                    None,
                ),

                direction_id=direction_id,
                direction_name=direction_name,

                has_primary_assignee=(
                    has_primary_assignee
                ),
                co_executor_count=(
                    co_executor_count
                ),

                primary_assignee_name=(
                    primary_assignee_name
                ),
                co_executor_names=(
                    co_executor_names
                ),

                review_place_labels=(
                    month_item_review_place_labels(
                        item.review_places
                    )
                ),
            )

            direction_block = blocks_by_direction.get(
                direction_id
            )

            if direction_block is None:
                direction_block = (
                    MonthPlanDirectionBlockDTO(
                        direction_id=direction_id,
                        direction_name=direction_name,
                        sort_order=(
                            direction_sort_order
                            if direction_sort_order is not None
                            else 9999
                        ),
                    )
                )

                blocks_by_direction[direction_id] = (
                    direction_block
                )

            direction_block.items.append(row_dto)

        return sorted(
            blocks_by_direction.values(),
            key=lambda block_dto: (
                block_dto.sort_order,
                block_dto.direction_id,
            ),
        )

    @staticmethod
    def _enum_value(value) -> str:
        if value is None:
            return ""

        return str(
            getattr(value, "value", value)
        )

    @staticmethod
    def _enum_label(value) -> str:
        if value is None:
            return "—"

        return str(
            getattr(value, "label_kz", None)
            or getattr(value, "label_ru", None)
            or getattr(value, "label", None)
            or getattr(value, "value", None)
            or value
        )

    # ---------------------------------------------------------
    # Получить или создать черновик
    # ---------------------------------------------------------
    @staticmethod
    async def get_or_create_draft(
            db: AsyncSession,
            *,
            school_id: int,
            school_plan_id: int,
            year: int,
            month: int,
    ):
        # 1) Проверяем месяц
        if month not in ACADEMIC_MONTHS:
            raise HTTPException(status_code=400, detail="Недопустимый месяц учебного года")

        # 2) Проверяем годовой план принадлежит школе
        school_plan = await SchoolMonthlyPlanRepo.get_school_plan_for_school(
            db,
            school_plan_id=school_plan_id,
            school_id=school_id,
        )
        if not school_plan:
            raise HTTPException(
                status_code=404,
                detail="Годовой план не найден (или не принадлежит школе)",
            )

        # 3) Проверяем статус годового плана
        if school_plan.status != PlanStatus.ACTIVE:
            raise HTTPException(
                status_code=400,
                detail="Месячное планирование доступно только для активного годового плана",
            )

        # 4) Получаем или создаём month_plan (ВАЖНО: добавлен year)
        month_plan, created = await SchoolMonthlyPlanRepo.get_or_create_month_plan(
            db,
            school_plan_id=school_plan_id,
            year=year,
            month=month,
        )

        # 5) Проверяем есть ли items
        count = await SchoolMonthlyPlanRepo.count_items(
            db,
            month_plan_id=month_plan.id,
        )

        # Если только создали или items пустые — строим
        if created or count == 0:
            await MonthPlanBuilder.build_items(
                db=db,
                school_plan_id=school_plan_id,
                month_plan_id=month_plan.id,
                month=month,
            )

        return month_plan

    # сохраняем и активируем месячный план
    @classmethod
    async def submit_month_plan(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
    ) -> None:
        month_plan = await SchoolMonthlyPlanRepo.get_month_plan_by_id(
            db, month_plan_id=month_plan_id
        )
        if not month_plan:
            raise HTTPException(status_code=404, detail="Месячный план не найден")

        if month_plan.status != PlanStatus.DRAFT:
            raise HTTPException(status_code=400, detail="План уже отправлен")

        items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan_id,
            with_source=True,
        )

        missing_week = [i for i in items if i.is_included and i.week_of_month is None]
        if missing_week:
            sample_ids = ", ".join(str(i.id) for i in missing_week[:10])
            raise HTTPException(
                status_code=400,
                detail=(
                    "У всех включённых задач должна быть выбрана неделя (1–6). "
                    f"Проблемные item_id: {sample_ids}"
                ),
            )

        weeks = month_weeks_grid(month_plan.year, month_plan.month)
        week_map = {w.week: w for w in weeks}

        invalid_week_items = []
        for it in items:
            if not it.is_included:
                continue

            wom = it.week_of_month
            wk = week_map.get(wom)
            if not wk:
                invalid_week_items.append(it.id)
                continue

            it.planned_start = wk.start
            it.planned_end = wk.end

        if invalid_week_items:
            sample = ", ".join(str(x) for x in invalid_week_items[:10])
            raise HTTPException(
                status_code=400,
                detail=(
                    "У некоторых задач выбрана неделя вне сетки этого месяца/года. "
                    f"Проблемные item_id: {sample}"
                ),
            )

        selected_quarter_rows = {}

        for item in items:
            row11 = item.source_row11

            if (
                    item.is_included
                    and row11 is not None
                    and row11.period_type == PlanPeriodType.QUARTER
            ):
                selected_quarter_rows[row11.id] = row11

        previous_quarter_months = (
            previous_months_in_quarter(
                month_plan.month
            )
        )

        existing_quarter_ids = (
            await SchoolMonthlyPlanRepo
            .list_previously_included_quarter_source_ids(
                db,
                school_plan_id=month_plan.school_plan_id,
                source_row11_ids=list(selected_quarter_rows),
                previous_months=previous_quarter_months,
            )
        )

        if existing_quarter_ids:
            duplicate_row = selected_quarter_rows[
                next(iter(existing_quarter_ids))
            ]
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Квартальная задача '{duplicate_row.topic}' "
                    "уже запланирована в этой четверти."
                ),
            )

        await db.flush()

        await SchoolMonthlyPlanRepo.set_month_plan_status(
            db,
            month_plan_id=month_plan_id,
            status=PlanStatus.ACTIVE,
        )

        await db.flush()

    @staticmethod
    async def get_month_plan(
            db: AsyncSession,
            *,
            month_plan_id: int,
    ):
        month_plan = await SchoolMonthlyPlanRepo.get_month_plan_by_id(
            db,
            month_plan_id=month_plan_id,
        )
        if not month_plan:
            raise HTTPException(404, "Месячный план не найден")
        return month_plan

    # удаления месячного плана (если черновик)
    @staticmethod
    async def delete_draft_month_plan(
            db: AsyncSession,
            *,
            month_plan_id: int,
            school_id: int,
    ):

        month_plan = await SchoolMonthlyPlanRepo.get_month_plan_for_school_by_id(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )

        if not month_plan:
            raise HTTPException(404, "Месячный план не найден")

        if month_plan.status != PlanStatus.DRAFT:
            raise HTTPException(
                400,
                "Удалять можно только черновик"
            )

        await SchoolMonthlyPlanRepo.delete_month_plan(
            db,
            month_plan=month_plan,
        )

        await db.flush()


class MonthCalendarService:
    @staticmethod
    async def get_plan_weeks(db: AsyncSession, *, month_plan_id: int) -> list[dict]:
        """
        Возвращает календарные недели месяца
        """
        mp = await SchoolMonthlyPlanRepo.get_month_plan_by_id(db, month_plan_id=month_plan_id)
        if not mp:
            raise HTTPException(status_code=404, detail="Месячный план не найден")

        weeks = month_weeks_grid(mp.year, mp.month)
        return [
            {"week": w.week, "start": w.start.isoformat(), "end": w.end.isoformat()}
            for w in weeks
        ]

    @staticmethod
    async def assign_week_to_item(
            db: AsyncSession,
            *,
            item_id: int,
            week_of_month: int,
    ) -> None:
        item = await SchoolMonthPlanItemRepo.get_item(db, item_id=item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Задача не найдена")

        mp = item.month_plan  # у тебя relationship selectin — нормально
        weeks = month_weeks_grid(mp.year, mp.month)
        wk = next((w for w in weeks if w.week == week_of_month), None)
        if not wk:
            raise HTTPException(status_code=400, detail="Неделя вне диапазона (1..6) для этого месяца")

        item.week_of_month = wk.week
        item.planned_start = wk.start
        item.planned_end = wk.end

        await db.flush()

    @staticmethod
    async def bulk_assign_week(
            db: AsyncSession,
            *,
            month_plan_id: int,
            item_ids: list[int],
            week_of_month: int,
    ) -> dict:
        mp = await SchoolMonthlyPlanRepo.get_month_plan_by_id(db, month_plan_id=month_plan_id)
        if not mp:
            raise HTTPException(status_code=404, detail="Месячный план не найден")

        weeks = month_weeks_grid(mp.year, mp.month)
        wk = next((w for w in weeks if w.week == week_of_month), None)
        if not wk:
            raise HTTPException(status_code=400, detail="Неделя вне диапазона (1..6) для этого месяца")

        items = await SchoolMonthPlanItemRepo.list_items_by_ids(db, month_plan_id=month_plan_id, item_ids=item_ids)

        # если часть id не принадлежит плану — просто игнорим (или можно ругаться)
        for it in items:
            it.week_of_month = wk.week
            it.planned_start = wk.start
            it.planned_end = wk.end

        await db.flush()
        return {"updated": len(items)}
