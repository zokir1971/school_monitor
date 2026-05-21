# schemas/checking_notebooks_dto.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.modules.reports.models_documents import TaskExecutionDocument
from app.modules.reports.models_template_reports import CheckingNotebooksReport, UserReportTemplate


@dataclass(slots=True)
class CheckingNotebooksDTO:
    month_item_id: int
    selected_report_id: int
    task_execution_document_id: int
    observer_user_id: int

    user_template_id: int | None = None

    school_name: str | None = None
    checker_name: str | None = None
    checker_post: str | None = None

    teacher_name: str | None = None
    class_name: str | None = None
    subject_name: str | None = None

    check_date: datetime | None = None

    rows_json: list[dict[str, Any]] = field(default_factory=list)

    total_score: int = 0
    max_score: int = 0
    percent: int = 0
    level: str = "—"

    conclusion: str | None = None
    recommendations: str | None = None


@dataclass
class CheckingNotebooksFillDTO:
    month_item_id: int
    selected_report_id: int
    task_execution_document_id: int

    schema: dict
    criteria: list
    score_scale: list[int]

    scores: dict
    saved_info: dict
    rows: list

    total_score: int
    max_score: int
    percent: int          # 👈 ДОБАВИТЬ
    level: str            # 👈 ДОБАВИТЬ

    report: CheckingNotebooksReport | None
    document: TaskExecutionDocument
    template: UserReportTemplate | None
