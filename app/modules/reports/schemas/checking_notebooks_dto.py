# schemas/checking_notebooks_dto.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.modules.reports.models_documents import (
    TaskExecutionDocument,
    TaskExecutionSelectedReport,
)
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

    rows_json: dict[str, Any] | list[dict[str, Any]] = field(default_factory=dict)

    total_score: int = 0
    max_score: int = 0
    percent: int = 0
    level: str = "—"

    conclusion: str | None = None
    recommendations: str | None = None


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
    full_name: str | None = None
    subject: str | None = None


@dataclass(slots=True)
class CheckingNotebooksFillContextDTO:
    """
    Быстрый read-context страницы заполнения проверки тетрадей.

    Формируется одним SQL-запросом и содержит только данные,
    необходимые сервису для GET /fill.

    Важно:
    - document может отсутствовать до первого Save/Complete;
    - report может отсутствовать до первого Save/Complete;
    - GET не должен создавать ни document, ни report.
    """

    selected_report: TaskExecutionSelectedReport

    report_code: str
    report_label: str

    school_id: int
    school_name: str

    academic_year: str = ""
    algorithm_parameters: dict = field(default_factory=dict)
    checker_post: str = ""

    teacher_name: str = ""
    teacher_subject: str = ""

    document: TaskExecutionDocument | None = None
    report: CheckingNotebooksReport | None = None


@dataclass(slots=True)
class CheckingNotebooksFillDTO:
    month_item_id: int
    selected_report_id: int
    task_execution_document_id: int | None

    schema: dict
    criteria: list
    score_scale: list[int]

    scores: dict
    saved_info: dict
    rows: list

    total_score: int
    max_score: int
    percent: int
    level: str

    report: CheckingNotebooksReport | None
    document: TaskExecutionDocument | None
    template: UserReportTemplate | None

    multiclass: bool = False
    can_multiclass: bool = False
    class_options: list = field(default_factory=list)
    class_checks: list = field(default_factory=list)
    class_totals: dict = field(default_factory=dict)
    notebook_revision: str = ""


@dataclass(slots=True)
class CheckingNotebooksFillPageDTO:
    month_item_id: int
    selected_report_id: int
    task_execution_document_id: int | None

    document: TaskExecutionDocument | None
    selected_report: TaskExecutionSelectedReport | None = None

    template: UserReportTemplate | None = None
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

    report: CheckingNotebooksReport | None = None
    readonly: bool = False
    error: str | None = None
