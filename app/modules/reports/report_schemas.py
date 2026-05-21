# app/modules/reports/report_schemas.py

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

from app.modules.reports.models_documents import TaskExecutionData


# =========================
# EXECUTION PAGE DTOs
# =========================

@dataclass(slots=True)
class StaffExecutionTaskDTO:
    month_item_id: int
    school_id: int | None = None

    week_of_month: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    period_text: str = "—"

    topic: str = "—"
    goal: str = "—"
    control_object: str = "—"
    control_type: str = "—"
    control_form: str = "—"
    review_place: str = "—"

    status: str = ""
    status_label: str = ""
    status_color: str = ""


@dataclass(slots=True)
class ExecutionFormDTO:
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

    @classmethod
    def from_model(cls, execution: TaskExecutionData | "ExecutionFormDTO" | None) -> "ExecutionFormDTO":
        if not execution:
            return cls()

        if isinstance(execution, cls):
            return execution

        grouped: dict[tuple[int, str], dict] = {}

        report_types: list[str] = []
        subjects: list[str] = []
        class_groups: list[str] = []
        parallel_classes: list[str] = []
        teacher_ids: list[str] = []

        for item in execution.selected_reports or []:
            report_type = item.report_type
            report_code = str(getattr(report_type, "code", "") or "").strip()

            if report_code and report_code not in report_types:
                report_types.append(report_code)

            report_type_id = getattr(report_type, "id", 0) or 0
            report_label = (
                    getattr(report_type, "name_kz", None)
                    or getattr(report_type, "name_ru", None)
                    or report_code
                    or "—"
            )

            key = (report_type_id, report_code or report_label)

            if key not in grouped:
                grouped[key] = {
                    "report_type_id": report_type_id,
                    "report_code": report_code,
                    "report_label": report_label,
                    "targets": [],
                }

            kind = str(item.target_kind or "").strip()
            value = str(item.target_value or "").strip()
            label = str(item.target_label or item.target_value or "").strip()

            grouped[key]["targets"].append(
                {
                    "kind": kind,
                    "value": value,
                    "label": label,
                }
            )

            if not value:
                continue

            if kind in {"subject", "subjects"} and value not in subjects:
                subjects.append(value)
            elif kind in {"class_group", "class_groups"} and value not in class_groups:
                class_groups.append(value)
            elif kind in {"parallel_class", "parallel_classes"} and value not in parallel_classes:
                parallel_classes.append(value)
            elif kind in {"teacher", "teacher_id", "teacher_ids"} and value not in teacher_ids:
                teacher_ids.append(value)

        teacher_id = teacher_ids[0] if len(teacher_ids) == 1 else ""

        return cls(
            control_scope=execution.control_scope or "",
            control_form=execution.control_form or "",
            control_kind=execution.control_kind or "",
            review_result=execution.review_result or "",
            report_types=report_types,
            subjects=subjects,
            class_groups=class_groups,
            parallel_classes=parallel_classes,
            teacher_id=teacher_id,
            teacher_ids=teacher_ids,
            generated_reports_json=json.dumps(
                list(grouped.values()),
                ensure_ascii=False,
            ),
        )


@dataclass(slots=True)
class CurrentDraftDTO:
    exists: bool = False
    document_id: int | None = None


# =========================
# CONTROL FLOW DTOs
# =========================

@dataclass(slots=True)
class SelectOptionDTO:
    code: str
    label: str


@dataclass(slots=True)
class DetailConfigDTO:
    """
    Конфигурация дополнительного блока слева:
    - type = "checkbox" -> renderCheckboxGroup
    - type = "select"   -> renderSingleSelect
    """
    label: str
    name: str
    type: str
    options: list[SelectOptionDTO] = field(default_factory=list)


@dataclass(slots=True)
class ControlFlowDTO:
    """
    Полный контракт для static/js/task_execute.js
    """
    scopes: list[SelectOptionDTO] = field(default_factory=list)
    forms_by_scope: dict[str, list[SelectOptionDTO]] = field(default_factory=dict)
    kinds: list[SelectOptionDTO] = field(default_factory=list)
    reports_by_scope: dict[str, list[SelectOptionDTO]] = field(default_factory=dict)
    details_by_scope: dict[str, DetailConfigDTO] = field(default_factory=dict)

    subjects: list[SelectOptionDTO] = field(default_factory=list)
    all_teachers: list[SelectOptionDTO] = field(default_factory=list)
    teachers_by_subject: dict[str, list[SelectOptionDTO]] = field(default_factory=dict)
    primary_teachers: list[SelectOptionDTO] = field(default_factory=list)


# =========================
# PAGE PAYLOAD DTO
# =========================

@dataclass(slots=True)
class StaffExecutionPagePayloadDTO:
    selected_task: StaffExecutionTaskDTO | None = None
    execution: ExecutionFormDTO | None = None
    current_draft: CurrentDraftDTO | None = None
    control_flow: dict[str, object] | None = None


@dataclass(slots=True)
class ExecutionPageBundle:
    current_draft: CurrentDraftDTO | None
    execution_data: TaskExecutionData | None
