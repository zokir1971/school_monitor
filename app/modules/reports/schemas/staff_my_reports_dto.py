# app/modules/reports/schemas/staff_my_reports_dto.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class StaffMyReportItemDTO:
    selected_report_id: int
    report_code: str
    title_ru: str
    title_kk: str
    target_label: str = ''
    status: str = 'pending'
    assigned_to: str = ''
    is_my_report: bool = False
    can_assign: bool = False
    fill_route: str | None = None
    pdf_route: str | None = None
    pdf_id: int | None = None
    has_draft: bool = False


@dataclass(slots=True)
class StaffMyReportTaskDTO:
    month_item_id: int

    topic: str = "—"

    planned_start: date | None = None
    planned_end: date | None = None
    period_text: str = "—"

    assigned_reports_count: int = 0
    reports: list[StaffMyReportItemDTO] = field(default_factory=list)
    is_primary: bool = False

    task_status: str = ""
    task_status_label: str = ""


@dataclass(slots=True)
class StaffMyReportsPageDTO:
    month: int

    tasks: list[StaffMyReportTaskDTO] = field(
        default_factory=list
    )
