# app/modules/reports/schemas/staff_my_reports_dto.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class StaffMyReportTaskDTO:
    month_item_id: int

    topic: str = "—"

    planned_start: date | None = None
    planned_end: date | None = None
    period_text: str = "—"

    assigned_reports_count: int = 0

    task_status: str = ""
    task_status_label: str = ""


@dataclass(slots=True)
class StaffMyReportsPageDTO:
    month: int

    tasks: list[StaffMyReportTaskDTO] = field(
        default_factory=list
    )
