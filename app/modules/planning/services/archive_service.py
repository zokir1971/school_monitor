# app/modules/planning/services/archive_service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.planning.enums import PlanStatus
from app.modules.planning.models_school import SchoolPlan
from app.modules.planning.repositories.month_plan_repository import (
    SchoolMonthlyPlanRepo,
)
from app.modules.planning.repositories.school_plan_repository import (
    SchoolPlanningRepo,
)
from app.modules.users.permissions import assert_can_edit_school


@dataclass(frozen=True, slots=True)
class ArchiveSchoolPlanResult:
    """
    Результат архивации учебного года школы.
    """

    plan_id: int
    school_id: int
    academic_year: str

    already_archived: bool
    archived_month_plans: int


class PlanningArchiveService:
    """
    Сервис архивации планирования ВШК.

    Архивация означает перевод структуры планирования
    учебного года в режим исторических данных.

    Архивируются:
        - SchoolPlan;
        - связанные SchoolMonthPlan.

    НЕ изменяются:
        - SchoolMonthPlanItem.status;
        - назначения исполнителей;
        - результаты выполнения;
        - документы;
        - отчёты;
        - PDF / QR;
        - результаты рассмотрения.

    Благодаря этому сохраняется фактическая история
    выполнения ВШК и статистика за учебный год.
    """

    @staticmethod
    async def archive_school_plan(
            db: AsyncSession,
            *,
            plan_id: int,
            user,
    ) -> ArchiveSchoolPlanResult:
        """
        Архивирует годовой план и все его месячные планы.

        Операция идемпотентна:
        повторная архивация уже архивного плана
        не считается ошибкой.

        Все изменения выполняются одной транзакцией.
        """

        # =====================================================
        # 1. PLAN
        # =====================================================

        plan = await db.get(
            SchoolPlan,
            plan_id,
        )

        if plan is None:
            raise HTTPException(
                status_code=404,
                detail="Годовой план ВШК не найден.",
            )

        # =====================================================
        # 2. ACCESS
        # =====================================================

        assert_can_edit_school(
            user,
            school_id=plan.school_id,
        )

        # =====================================================
        # 3. IDEMPOTENCY
        # =====================================================

        current_status = (
            plan.status.value
            if hasattr(plan.status, "value")
            else str(plan.status)
        )

        if current_status == PlanStatus.ARCHIVED.value:
            return ArchiveSchoolPlanResult(
                plan_id=plan.id,
                school_id=plan.school_id,
                academic_year=plan.academic_year,
                already_archived=True,
                archived_month_plans=0,
            )

        # =====================================================
        # 4. ACADEMIC YEAR
        # =====================================================

        PlanningArchiveService._validate_academic_year_is_finished(
            plan.academic_year,
            today=date.today(),
        )

        # =====================================================
        # 5. ARCHIVE
        # =====================================================

        try:
            archived_month_plans = (
                await SchoolMonthlyPlanRepo
                .archive_month_plans_by_school_plan(
                    db,
                    school_plan_id=plan.id,
                )
            )

            updated = (
                await SchoolPlanningRepo
                .set_school_plan_status(
                    db,
                    plan_id=plan.id,
                    school_id=plan.school_id,
                    status=PlanStatus.ARCHIVED,
                )
            )

            if not updated:
                raise HTTPException(
                    status_code=404,
                    detail="Годовой план ВШК не найден.",
                )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

        # =====================================================
        # 6. RESULT
        # =====================================================

        return ArchiveSchoolPlanResult(
            plan_id=plan.id,
            school_id=plan.school_id,
            academic_year=plan.academic_year,
            already_archived=False,
            archived_month_plans=archived_month_plans,
        )

    @staticmethod
    def _validate_academic_year_is_finished(
            academic_year: str,
            *,
            today: date,
    ) -> None:
        """
        Запрещает ручную архивацию незавершённого
        учебного года.

        Ожидаемый формат:
            2025-2026
        """

        try:
            start_year_text, end_year_text = (
                academic_year.split("-", maxsplit=1)
            )

            start_year = int(start_year_text)
            end_year = int(end_year_text)

        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Некорректный формат учебного года."
                ),
            )

        if end_year != start_year + 1:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Некорректный учебный год."
                ),
            )

        # Учебный год считаем завершённым после июня.
        academic_year_end = date(
            end_year,
            6,
            30,
        )

        if today <= academic_year_end:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Учебный год {academic_year} "
                    "ещё не завершён."
                ),
            )
