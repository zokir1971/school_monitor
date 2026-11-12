# app/modules/reports/services/staff_my_reports_service.py

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.repositories.my_report_catalog_repo import MyReportCatalogRepo
from app.modules.reports.schemas.staff_my_reports_dto import (
    StaffMyReportTaskDTO,
    StaffMyReportItemDTO,
    StaffMyReportsPageDTO,
)
from app.modules.users.models import User
from app.modules.reports.services.base_report_service import BaseReportService


class StaffMyReportsService:
    """
    Сервис быстрого входа сотрудника в назначенные ему отчеты.

    Назначение:
    - показать выбранные отчёты задач ответственного и назначения сотрудника;
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

    _require_user_context = staticmethod(BaseReportService.require_user_context)

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

        Ответственный видит выбранные отчёты своих задач, включая нераспределённые.
        Остальные сотрудники видят свои назначения. Данные загружаются пакетно.
        """

        cls._validate_month(month)

        school_id, staff_member_id = (
            cls._require_user_context(user)
        )

        rows=await MyReportCatalogRepo.list_reports(db,school_id=school_id,staff_member_id=staff_member_id,month=month)
        grouped={}
        for row in rows:
            task_id=int(row['month_item_id'])
            if task_id not in grouped:
                grouped[task_id]=StaffMyReportTaskDTO(month_item_id=task_id,topic=str(row.get('topic') or '—'),
                    planned_start=row['planned_start'],planned_end=row['planned_end'],
                    period_text=cls._build_period_text(row['planned_start'],row['planned_end']),
                    task_status=cls._status_value(row['task_status']),task_status_label=cls._status_label(row['task_status']),
                    is_primary=bool(row['is_primary']))
            task=grouped[task_id]
            mine=row['assigned_staff_id']==staff_member_id
            state=cls._status_value(row['assignment_status'])
            doc_status=cls._status_value(row['document_status'])
            finished=doc_status in ('submitted','approved','accepted') or state=='completed'
            if row['assigned_staff_id'] is None:state='unassigned'
            elif state!='waived' and finished:state='completed'
            elif state!='waived' and row['document_id']:state='draft'
            elif not state:state='pending'
            not_archived=all(cls._status_value(row[k])!='archived' for k in ('monthly_status','annual_status'))
            # This catalog only displays status. Source choice and editing belong
            # to the existing task preparation page and its assignment service.
            task.reports.append(StaffMyReportItemDTO(selected_report_id=int(row['selected_report_id']),report_code=row['report_code'],
                title_ru=row['name_ru'] or row['name_kz'] or row['report_code'],title_kk=row['name_kz'] or row['name_ru'] or row['report_code'],
                target_label=row['target_label'] or '',status=state,assigned_to=row['assigned_to'] or '',
                is_my_report=mine,can_assign=bool(row['is_primary']) and not_archived and not row['completed_at'],
                has_draft=bool(row['document_id']) and not finished))
            if mine:task.assigned_reports_count+=1
        return StaffMyReportsPageDTO(month=month,tasks=list(grouped.values()))

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
        - текущему сотруднику назначен отчёт либо он ответственный за задачу.

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
            MyReportCatalogRepo
            .has_task_access(
                db,
                school_id=school_id,
                staff_member_id=staff_member_id,
                month_item_id=month_item_id,
            )
        )

        if not has_access:
            raise ValueError(
                "Нет доступа к отчётам выбранной задачи."
            )
