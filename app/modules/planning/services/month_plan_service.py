# app/modules/planning/services/month_plan_service.py
from fastapi import HTTPException
from app.modules.planning.utils.month_schedule import MonthSchedule
from app.modules.planning.repositories.month_correction_repo import MonthCorrectionRepo
from app.modules.planning.services.month_correction_service import MonthCorrectionService
from app.modules.planning.utils.month_plan_readiness import month_plan_readiness, enum_value
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


async def _guard_month_plan_edit(
        db: AsyncSession,
        *,
        month_plan_id: int,
):
    """
    Единая точка защиты изменения месячного плана.

    Проверяет:
    - месячный план существует;
    - месячный план не архивирован;
    - родительский годовой план существует;
    - родительский годовой план не архивирован.

    Архивные планы остаются доступными для просмотра,
    но не для изменения.
    """

    # =====================================================
    # 1. MONTH PLAN
    # =====================================================

    month_plan = (
        await SchoolMonthlyPlanRepo.get_month_plan_by_id(
            db,
            month_plan_id=month_plan_id,
        )
    )

    if not month_plan:
        raise HTTPException(
            status_code=404,
            detail="Месячный план не найден",
        )

    # =====================================================
    # 2. MONTH PLAN ARCHIVE GUARD
    # =====================================================

    if month_plan.status == PlanStatus.ARCHIVED:
        raise HTTPException(
            status_code=409,
            detail=(
                "Мұрағатталған айлық жоспарды "
                "өзгертуге болмайды."
            ),
        )

    # =====================================================
    # 3. SCHOOL PLAN
    # =====================================================

    school_plan = await SchoolMonthlyPlanRepo.get_school_plan(
        db,
        school_plan_id=month_plan.school_plan_id,
    )

    if not school_plan:
        raise HTTPException(
            status_code=404,
            detail="Годовой план не найден",
        )

    # SchoolPlan.status сейчас строковый.
    school_plan_status = (
        school_plan.status.value
        if hasattr(school_plan.status, "value")
        else str(school_plan.status)
    )

    # =====================================================
    # 4. SCHOOL PLAN ARCHIVE GUARD
    # =====================================================

    if school_plan_status == PlanStatus.ARCHIVED.value:
        raise HTTPException(
            status_code=409,
            detail=(
                "Мұрағатталған оқу жылының "
                "айлық жоспарын өзгертуге болмайды."
            ),
        )

    return month_plan


class SchoolMonthlyPlanningService:
    @classmethod
    async def build_month_plan_direction_blocks(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
            schedule_data=None,
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

        if schedule_data is None:
            schedule_data=await SchoolMonthlyPlanRepo.schedule_snapshot(db,month_plan_id=month_plan_id)
        schedule=await MonthSchedule.evaluate(db,schedule_data)
        items=[item for item in items if item.id in schedule['visible_ids']]

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
                schedule_warning=item.id in schedule['warning_ids'],
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

        if enum_value(month_plan.status)=='archived':
            raise HTTPException(409,'Архивный план нельзя обновлять / Мұрағат жоспарын жаңартуға болмайды')
        # Add newly eligible rows without resetting existing flags or history.
        await MonthPlanBuilder.build_items(db=db,school_plan_id=school_plan_id,month_plan_id=month_plan.id,month=month,default_included=created or enum_value(month_plan.status)=='draft')

        return month_plan

    # сохраняем и активируем месячный план
    @classmethod
    async def submit_month_plan(
            cls,
            db: AsyncSession,
            *,
            month_plan_id: int,
            school_id: int,
    ) -> None:
        data = await MonthCorrectionRepo.snapshot(db, school_id=school_id, month_plan_id=month_plan_id, lock=True)
        if not data:
            raise HTTPException(404, 'Месячный план не найден / Айлық жоспар табылмады')
        if enum_value(data['plan']['status']) != 'draft':
            raise HTTPException(409, 'План уже отправлен или архивирован / Жоспар жіберілген немесе мұрағатталған')
        schedule=await MonthSchedule.evaluate(db,data)
        invalid={item['id'] for item in data['items'] if item['is_included']}-schedule['eligible_ids']
        if invalid:
            numbers=', '.join(map(str,sorted(invalid)))
            raise HTTPException(409,f'Проверьте сроки включённых задач: №{numbers}. Они не соответствуют месяцу либо уже выполнены в этой четверти. / Енгізілген тапсырмалардың мерзімдерін тексеріңіз: №{numbers}. Олар айға сәйкес келмейді немесе осы тоқсанда орындалған.')
        readiness = month_plan_readiness(data, month_weeks_grid(data['plan']['year'], data['plan']['month']))
        if not readiness['included'] or readiness['problems']:
            raise HTTPException(400, 'План не отправлен. Проверьте недели и ответственных включённых задач. / Жоспар жіберілмеді. Енгізілген тапсырмалардың апталарын және жауаптыларын тексеріңіз.')
        month_plan = await _guard_month_plan_edit(
            db,
            month_plan_id=month_plan_id,
        )

        if not month_plan:
            raise HTTPException(status_code=404, detail="Месячный план не найден")

        if month_plan.status != PlanStatus.DRAFT:
            raise HTTPException(status_code=400, detail="План уже отправлен")

        items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan_id,
            with_source=True,
            refresh=True,
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
            .list_previously_completed_quarter_source_ids(
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
                    "уже выполнена в этой четверти."
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
            plan_revision: str = "",
            confirmed_plan_id: str = "",
    ):

        data = await MonthCorrectionRepo.snapshot(db, school_id=school_id, month_plan_id=month_plan_id, lock=True)
        if not data:
            raise HTTPException(404, 'Месячный план не найден / Айлық жоспар табылмады')
        readiness = month_plan_readiness(data, month_weeks_grid(data['plan']['year'], data['plan']['month']))
        if not readiness['can_delete']:
            raise HTTPException(409, 'Удаление запрещено: в плане есть назначения, сроки или данные задач либо план уже отправлен/архивирован. / Жоюға тыйым салынған: жоспарда тағайындаулар, мерзімдер немесе тапсырма деректері бар не жоспар жіберілген/мұрағатталған.')
        if confirmed_plan_id != str(month_plan_id) or plan_revision != MonthCorrectionService.revision(data):
            raise HTTPException(409, 'Подтвердите удаление на обновлённой странице плана. / Жаңартылған жоспар бетінде жоюды растаңыз.')
        month_plan = await SchoolMonthlyPlanRepo.get_month_plan_for_school_by_id(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )

        if not month_plan:
            raise HTTPException(404, "Айлық жоспар табылмады")

        if month_plan.status == PlanStatus.ARCHIVED:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Мұрағатталған айлық жоспарды "
                    "жоюға болмайды."
                ),
            )

        if month_plan.status != PlanStatus.DRAFT:
            raise HTTPException(
                400,
                "Тек қана черновик жоспарды жоюға болады"
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
        item = await SchoolMonthPlanItemRepo.get_item(
            db,
            item_id=item_id,
        )

        if not item:
            raise HTTPException(
                status_code=404,
                detail="Задача не найдена",
            )

        mp = item.month_plan

        await _guard_month_plan_edit(
            db,
            month_plan_id=mp.id,
        )

        weeks = month_weeks_grid(
            mp.year,
            mp.month,
        )

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
        mp = await _guard_month_plan_edit(
            db,
            month_plan_id=month_plan_id,
        )

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
