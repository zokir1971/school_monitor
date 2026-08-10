# app/modules/reports/services/staff_my_reports_service.py

from __future__ import annotations

from datetime import date
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.repositories.report_assignment_repo import (
    ReportAssignmentRepo,
)
from app.modules.reports.schemas.staff_my_reports_dto import (
    StaffMyReportTaskDTO,
    StaffMyReportsPageDTO,
)
from app.modules.users.models import User


class StaffMyReportsService:
    """
    Сервис быстрого входа сотрудника в назначенные ему отчеты.

    Назначение:
    - показать задачи выбранного месяца, в которых сотруднику
      назначен хотя бы один конкретный отчет;
    - подготовить DTO для страницы выбора задачи;
    - проверить доступ к выбранной задаче перед переходом
      на страницу подготовки отчетов.

    Сервис НЕ отвечает за:
    - принятие задачи в работу;
    - построение алгоритма исполнения;
    - выбор типов отчетов;
    - распределение отчетов между исполнителями.

    Эти этапы выполняются ранее в основном workflow задачи.
    """

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _build_period_text(
        planned_start: date | None,
        planned_end: date | None,
    ) -> str:
        """
        Сформировать отображаемый срок выполнения задачи.
        """

        if planned_start and planned_end:
            if planned_start == planned_end:
                return planned_start.strftime("%d.%m.%Y")

            return (
                f"{planned_start.strftime('%d.%m.%Y')} – "
                f"{planned_end.strftime('%d.%m.%Y')}"
            )

        if planned_start:
            return planned_start.strftime("%d.%m.%Y")

        if planned_end:
            return f"до {planned_end.strftime('%d.%m.%Y')}"

        return "—"

    @staticmethod
    def _status_value(status: Any) -> str:
        """
        Получить техническое значение статуса независимо от того,
        пришел Enum или строка.
        """

        if status is None:
            return ""

        return str(
            getattr(
                status,
                "value",
                status,
            )
        )

    @staticmethod
    def _status_label(status: Any) -> str:
        """
        Получить отображаемую подпись статуса.
        В проекте приоритет отдаем казахской подписи Enum.
        """

        if status is None:
            return ""

        return str(
            getattr(status, "label_kz", None)
            or getattr(status, "label_ru", None)
            or getattr(status, "label", None)
            or getattr(status, "value", None)
            or status
        )

    @staticmethod
    def _require_user_context(
        user: User,
    ) -> tuple[int, int]:
        """
        Получить школьный контекст текущего пользователя.

        Для быстрого входа в отчеты обязательно должны быть известны:
        - school_id;
        - staff_member_id.
        """

        if user.school_id is None:
            raise ValueError(
                "У пользователя не определена школа."
            )

        if user.staff_member_id is None:
            raise ValueError(
                "Для пользователя не найден сотрудник школы."
            )

        return (
            cast(int, user.school_id),
            cast(int, user.staff_member_id),
        )

    @staticmethod
    def _validate_month(month: int) -> None:
        if not 1 <= month <= 12:
            raise ValueError(
                "Некорректный номер месяца."
            )

    # =========================================================
    # PAGE
    # =========================================================

    @classmethod
    async def get_page(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month: int,
    ) -> StaffMyReportsPageDTO:
        """
        Получить страницу быстрого доступа к отчетам сотрудника.

        Возвращаются только те задачи выбранного месяца,
        в которых текущему сотруднику назначен хотя бы один отчет
        через TaskSelectedReportAssignment.
        """

        cls._validate_month(month)

        school_id, staff_member_id = (
            cls._require_user_context(user)
        )

        rows = await (
            ReportAssignmentRepo
            .list_report_tasks_for_staff(
                db,
                school_id=school_id,
                staff_member_id=staff_member_id,
                month=month,
            )
        )

        tasks: list[StaffMyReportTaskDTO] = []

        for row in rows:
            planned_start = row.get("planned_start")
            planned_end = row.get("planned_end")
            task_status = row.get("task_status")

            tasks.append(
                StaffMyReportTaskDTO(
                    month_item_id=int(
                        row["month_item_id"]
                    ),
                    topic=str(
                        row.get("topic")
                        or "—"
                    ),
                    planned_start=planned_start,
                    planned_end=planned_end,
                    period_text=cls._build_period_text(
                        planned_start,
                        planned_end,
                    ),
                    assigned_reports_count=int(
                        row.get(
                            "assigned_reports_count",
                            0,
                        )
                        or 0
                    ),
                    task_status=cls._status_value(
                        task_status
                    ),
                    task_status_label=cls._status_label(
                        task_status
                    ),
                )
            )

        return StaffMyReportsPageDTO(
            month=month,
            tasks=tasks,
        )

    # =========================================================
    # ACCESS TO SELECTED TASK
    # =========================================================

    @classmethod
    async def ensure_task_access(
        cls,
        db: AsyncSession,
        *,
        user: User,
        month_item_id: int,
    ) -> None:
        """
        Проверить право сотрудника перейти к отчетам задачи.

        Доступ разрешается только если:
        - задача принадлежит школе пользователя;
        - текущему сотруднику назначен хотя бы один отчет задачи.

        Метод специально ничего не возвращает:
        отсутствие исключения означает разрешенный переход.
        """

        if month_item_id <= 0:
            raise ValueError(
                "Некорректный идентификатор задачи."
            )

        school_id, staff_member_id = (
            cls._require_user_context(user)
        )

        has_access = await (
            ReportAssignmentRepo
            .has_report_assignment_for_task(
                db,
                school_id=school_id,
                staff_member_id=staff_member_id,
                month_item_id=month_item_id,
            )
        )

        if not has_access:
            raise ValueError(
                "Для выбранной задачи вам не назначены отчеты."
            )
