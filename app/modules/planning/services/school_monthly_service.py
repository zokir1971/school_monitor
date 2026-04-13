# app/modules/planning/services/school_monthly_service.py
import re

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanStatus, PlanPeriodType
from app.modules.planning.models_month_plan import SchoolMonthPlanItem
from app.modules.planning.models_school import SchoolPlanRow11
from app.modules.planning.repo_monthly import (
    SchoolMonthlyPlanRepo,
    ACADEMIC_MONTHS, SchoolMonthPlanItemRepo,
)

from app.utils.calendar_weeks import month_weeks_grid


class SchoolMonthlyPlanningService:
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
            await SchoolMonthlyPlanningService._build_items_for_month(
                db=db,
                school_plan_id=school_plan_id,
                month_plan_id=month_plan.id,
                month=month,
            )

        return month_plan

    # ---------------------------------------------------------
    # Формирование items по period_type
    # ---------------------------------------------------------
    @staticmethod
    def _parse_int_set(v) -> set[int]:
        """
        Поддержка:
          - int (3)
          - str: "3", "3,4", "3; 4", "3 4"
          - None -> empty set
        """
        if v is None:
            return set()

        if isinstance(v, int):
            return {v}

        if isinstance(v, str):
            nums = re.findall(r"\d+", v)
            return {int(x) for x in nums}

        # fallback
        try:
            return {int(v)}
        except (ValueError, TypeError):
            return set()

    @staticmethod
    def _parse_months_values(period_values: str | None) -> set[int]:
        """
        period_values: "9;3;5" или "9, 3, 5"
        Возвращает {9,3,5}
        """
        raw = (period_values or "").strip()
        if not raw:
            return set()

        parts = raw.replace(";", ",").split(",")
        out: set[int] = set()
        for p in parts:
            p2 = (p or "").strip()
            if not p2:
                continue
            try:
                out.add(int(p2))
            except ValueError:
                # мусор игнорируем
                continue
        return out

    @staticmethod
    def _quarter_of_month(m: int) -> int:
        return (m - 1) // 3 + 1

    @staticmethod
    def _quarter_months(m: int) -> list[int]:
        if m in (9, 10):
            return [9, 10]
        if m in (11, 12):
            return [11, 12]
        if m in (1, 2, 3):
            return [1, 2, 3]
        if m in (4, 5):
            return [4, 5]
        return []

    @staticmethod
    def _previous_months_in_quarter(m: int) -> list[int]:
        months = SchoolMonthlyPlanningService._quarter_months(m)
        result: list[int] = []

        for x in months:
            if x == m:
                break
            result.append(x)

        return result

    @staticmethod
    async def _build_items_for_month(
            db: AsyncSession,
            *,
            school_plan_id: int,
            month_plan_id: int,
            month: int,
    ) -> None:
        """
        Собирает элементы месячного плана из строк годового плана
        и переносит места рассмотрения (review_places).

        Порядок групп сохраняется:
        1) конкретный месяц
        2) несколько месяцев
        3) ежемесячно
        4) весь учебный год
        5) ежеквартально

        Для QUARTER:
        - если задача уже была включена в предыдущих месяцах текущей четверти,
          в текущий черновик не добавляем её вообще;
        - если не была, добавляем выключенной (is_included=False).
        """
        if not (1 <= month <= 12):
            raise ValueError(f"month must be 1..12, got {month}")

        rows = await SchoolMonthlyPlanRepo.list_source_rows11_for_school_plan(
            db,
            school_plan_id=school_plan_id,
        )

        print(
            "BUILD rows:",
            len(rows),
            "school_plan_id=",
            school_plan_id,
            "month=",
            month,
        )

        academic_months = {9, 10, 11, 12, 1, 2, 3, 4, 5}
        in_academic = month in academic_months
        target_q = SchoolMonthlyPlanningService._quarter_of_month(month)

        month_ids: list[int] = []
        months_ids: list[int] = []
        monthly_ids: list[int] = []
        all_year_ids: list[int] = []
        quarter_ids: list[int] = []

        skipped_quarter_ids: list[int] = []

        row_map: dict[int, SchoolPlanRow11] = {}

        for row in rows:
            row_map[row.id] = row

            pt = row.period_type
            pt_val = pt.value if hasattr(pt, "value") else pt

            if pt_val == PlanPeriodType.MONTH.value:
                pv = getattr(row, "period_value_int", None)
                try:
                    pv_int = int(pv) if pv is not None else None
                except (TypeError, ValueError):
                    pv_int = None

                if pv_int == month:
                    month_ids.append(row.id)
                continue

            if pt_val == PlanPeriodType.MONTHS.value:
                months_set = SchoolMonthlyPlanningService._parse_months_values(
                    getattr(row, "period_values", None)
                )
                if month in months_set:
                    months_ids.append(row.id)
                continue

            if pt_val == PlanPeriodType.MONTHLY.value:
                if in_academic:
                    monthly_ids.append(row.id)
                continue

            if pt_val == PlanPeriodType.ALL_YEAR.value:
                if in_academic:
                    all_year_ids.append(row.id)
                continue

            if pt_val == PlanPeriodType.QUARTER.value:
                if not in_academic:
                    continue

                pv_raw = getattr(row, "period_value_int", None)
                pv_set = SchoolMonthlyPlanningService._parse_int_set(pv_raw)

                if pv_raw is not None and pv_set and target_q not in pv_set:
                    continue

                already_in_previous_months = (
                    await SchoolMonthlyPlanRepo.quarterly_already_included_before_current_month(
                        db,
                        school_plan_id=school_plan_id,
                        source_row11_id=row.id,
                        target_month=month,
                    )
                )

                if already_in_previous_months:
                    skipped_quarter_ids.append(row.id)
                    continue

                quarter_ids.append(row.id)
                continue

            print("WARN: unknown period_type:", pt_val, "row_id=", row.id)

        print(
            "BUILD counts:",
            "month=", len(month_ids),
            "months=", len(months_ids),
            "monthly=", len(monthly_ids),
            "all_year=", len(all_year_ids),
            "quarter=", len(quarter_ids),
            "skipped_quarter=", len(skipped_quarter_ids),
            "target_q=", target_q,
            "in_academic=", in_academic,
        )

        non_quarter_ids = month_ids + months_ids + monthly_ids + all_year_ids

        created_items: list[SchoolMonthPlanItem] = []

        if non_quarter_ids:
            created_items.extend(
                await SchoolMonthlyPlanRepo.create_items_bulk(
                    db,
                    month_plan_id=month_plan_id,
                    source_row11_ids=non_quarter_ids,
                    default_included=True,
                    default_week=None,
                )
            )

        if quarter_ids:
            created_items.extend(
                await SchoolMonthlyPlanRepo.create_items_bulk(
                    db,
                    month_plan_id=month_plan_id,
                    source_row11_ids=quarter_ids,
                    default_included=False,
                    default_week=None,
                )
            )

        review_place_rows: list[dict] = []

        for item in created_items:
            source_row11_id = getattr(item, "source_row11_id", None)
            if source_row11_id is None:
                continue

            source_row11_id = int(source_row11_id)

            row = row_map.get(source_row11_id)
            if not row:
                continue

            for rp in (row.review_places or []):
                review_place_value = (
                    rp.review_place.value
                    if hasattr(rp.review_place, "value")
                    else rp.review_place
                )

                review_place_rows.append(
                    {
                        "month_item_id": item.id,
                        "review_place": review_place_value,
                    }
                )

        if review_place_rows:
            await SchoolMonthPlanItemRepo.create_month_item_review_places_bulk(
                db,
                rows=review_place_rows,
            )

        await db.flush()

        print(
            "BUILD: flush OK",
            "month_plan_id=", month_plan_id,
            "created_items=", len(created_items),
            "review_places=", len(review_place_rows),
        )

    # сохраняем и активируем месячный план
    @staticmethod
    async def submit_month_plan(
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

        items = await SchoolMonthlyPlanRepo.list_items(db, month_plan_id=month_plan_id)

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

        for it in items:
            if not it.is_included:
                continue

            src = it.source_row11
            if not src:
                continue

            if src.period_type == PlanPeriodType.QUARTER:
                exists = await SchoolMonthlyPlanRepo.quarterly_already_included_before_current_month(
                    db,
                    school_plan_id=month_plan.school_plan_id,
                    source_row11_id=src.id,
                    target_month=month_plan.month,
                )
                if exists:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Квартальная задача '{src.topic}' уже запланирована в этой четверти.",
                    )

        await db.flush()

        await SchoolMonthlyPlanRepo.set_month_plan_status(
            db,
            month_plan_id=month_plan_id,
            status=PlanStatus.ACTIVE,
        )

        await db.commit()

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
            month_plan=month_plan
        )

        await db.commit()


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

        await db.commit()

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

        await db.commit()
        return {"updated": len(items)}
