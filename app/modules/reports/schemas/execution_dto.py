# app/modules/reports/schemas/execution_dto.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ExecutionFormDTO:
    """
    Состояние формы выполнения задачи для UI.
    """

    control_scope: str = ""
    control_form: str = ""
    control_kind: str = ""
    review_result: str = ""

    report_types: list[str] = field(default_factory=list)

    subjects: list[str] = field(default_factory=list)
    class_groups: list[str] = field(default_factory=list)
    parallel_classes: list[str] = field(default_factory=list)

    teacher_id: str = ""
    teacher_ids: list[str] = field(default_factory=list)

    generated_reports_json: str = "[]"


@dataclass(slots=True)
class CurrentDraftDTO:
    """
    Краткое состояние текущего черновика выполнения задачи.
    """

    exists: bool = False
    document_id: int | None = None
