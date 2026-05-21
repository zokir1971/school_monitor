# app/modules/reports/system_report_dto/system_checking_notebooks_dto.py

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SchoolInfoDTO:
    id: int
    name: str


@dataclass(slots=True)
class CheckerInfoDTO:
    full_name: str
    post: str


@dataclass(slots=True)
class TeacherInfoDTO:
    full_name: str
    subject: str | None


# =========================================================
# REPORT DTO
# =========================================================

@dataclass(slots=True)
class CheckingNotebooksReportDTO:
    id: int

    submitted_at: datetime | None = None

    qr_file: str | None = None
    pdf_signed_file: str | None = None

    rows_json: list[dict[str, Any]] = field(default_factory=list)

    info_json: dict[str, Any] = field(default_factory=dict)


# =========================================================
# FILL PAGE DTO
# =========================================================

@dataclass(slots=True)
class CheckingNotebooksFillPageDTO:
    month_item_id: int
    selected_report_id: int
    task_execution_document_id: int

    document: Any
    selected_report: Any | None = None

    template: Any | None = None
    schema: dict[str, Any] = field(default_factory=dict)

    rows: list[dict[str, Any]] = field(default_factory=list)
    saved_info: dict[str, Any] = field(default_factory=dict)

    criteria: list[Any] = field(default_factory=list)
    score_scale: list[Any] = field(default_factory=list)

    scores: dict[str, Any] = field(default_factory=dict)
    total_score: int = 0
    max_score: int = 0
    percent: int = 0
    level: str = "—"

    report: Any | None = None
    readonly: bool = False
    error: str | None = None
