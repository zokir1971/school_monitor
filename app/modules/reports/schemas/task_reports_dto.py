# app/modules/reports/schemas/task_reports_dto.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.modules.planning.enums import PlanItemStatus
from app.modules.reports.enums import (
    DocumentType,
    TaskDocumentSource,
    TaskDocumentStatus,
)


@dataclass(slots=True)
class TaskReportListItemDTO:
    """
    Один выбранный отчет задачи на рабочей странице.
    """

    selected_report_id: int
    report_type_id: int | None

    report_code: str
    report_label: str

    target_kind: str | None = None
    target_value: str | None = None
    target_label: str | None = None

    assigned_staff_member_id: int | None = None
    is_my_report: bool = False

    target_valid: bool = True
    target_error: str | None = None

    document_id: int | None = None
    document_status: TaskDocumentStatus | None = None

    is_filled: bool = False
    is_completed: bool = False
    has_draft: bool = False

    source: TaskDocumentSource | None = None

    is_system_used: bool = False
    is_user_template_used: bool = False

    has_system_template: bool = False
    has_user_template: bool = False

    can_fill_system_report: bool = False
    can_view_system_report: bool = False

    system_fill_route: str | None = None
    system_pdf_view_route: str | None = None

    system_report_id: int | None = None
    system_pdf_signed_file: str | None = None

    can_fill_user_report: bool = False
    can_view_user_report: bool = False

    user_fill_route: str | None = None
    user_pdf_view_route: str | None = None

    user_report_id: int | None = None
    user_pdf_signed_file: str | None = None

    custom_template_id: int | None = None
    template_mode: str | None = None


@dataclass(slots=True)
class TaskReportsPageDTO:
    """
    Рабочая страница отчетов по задаче.
    """

    month_item_id: int

    task_title: str | None = None
    task_topic: str = "—"
    task_month: int | None = None

    planned_start: date | None = None
    planned_end: date | None = None
    period_text: str = "—"

    task_status: PlanItemStatus | None = None

    current_staff_member_id: int | None = None

    is_primary_executor: bool = False
    is_co_executor: bool = False
    executor_role_label: str = "—"

    my_reports: list[TaskReportListItemDTO] = field(default_factory=list)
    all_reports: list[TaskReportListItemDTO] = field(default_factory=list)

    # Совместимость с текущим template_reports.html.
    # Удалить после перевода шаблона на my_reports/all_reports.
    reports: list[TaskReportListItemDTO] = field(default_factory=list)

    completion_mode: str | None = None

    is_simple_final_document: bool = False
    is_final_with_system_reports: bool = False

    required_reports_count: int = 0
    completed_reports_count: int = 0
    signed_reports_count: int = 0

    pending_reports_count: int = 0
    waived_reports_count: int = 0

    all_reports_resolved: bool = False
    can_manage_report_assignments: bool = False

    all_reports_completed: bool = False
    all_reports_signed: bool = False

    final_documents: list[ExecutionFinalDocumentDTO] = field(default_factory=list)
    current_final_document: ExecutionFinalDocumentDTO | None = None

    has_final_document: bool = False
    final_document_status: TaskDocumentStatus | None = None

    review_reports_text: str | None = None
    review_place_text: str | None = None


@dataclass(slots=True)
class ExecutionFinalDocumentDTO:
    id: int
    status: TaskDocumentStatus | None = None
    document_type: DocumentType | None = None
    original_file_name: str | None = None
    file_path: str | None = None
    is_final: bool = False
