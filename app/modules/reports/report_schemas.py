# app/modules/reports/report_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.modules.planning.enums import ResponsibleRole, AssignmentKind
from app.modules.reports.models_documents import TaskExecutionData
from app.modules.reports.schemas.execution_dto import ExecutionFormDTO, CurrentDraftDTO


# =========================
# TASK PARTICIPANTS DTOs
# =========================
@dataclass(slots=True)
class StaffTaskParticipantDTO:
    """
    Участник выполнения задачи месячного плана.
    """
    staff_member_id: int
    staff_role_id: int

    full_name: str

    position_text: str = ""

    role: ResponsibleRole | None = None
    role_label: str = ""

    assignment_kind: AssignmentKind | None = None
    assignment_kind_label: str = ""

    is_current_user: bool = False


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
    control_form_ru: str = "—"
    control_methods: str = "—"
    review_place_ru: str = "—"
    review_place: str = "—"

    status: str = ""
    status_label: str = ""
    status_color: str = ""

    responsible: StaffTaskParticipantDTO | None = None

    co_executors: list[StaffTaskParticipantDTO] = field(
        default_factory=list
    )

    current_user_role: str = ""
    current_user_role_label: str = ""

    can_execute: bool = False
    can_view: bool = True

    has_execution: bool = False
    has_draft: bool = False
    has_submitted_document: bool = False






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

    options: list[SelectOptionDTO] = field(
        default_factory=list
    )


@dataclass(slots=True)
class ControlFlowDTO:
    """
    Полный контракт для static/js/task_execute.js.
    """

    scopes: list[SelectOptionDTO] = field(
        default_factory=list
    )

    forms_by_scope: dict[
        str,
        list[SelectOptionDTO],
    ] = field(default_factory=dict)

    kinds: list[SelectOptionDTO] = field(
        default_factory=list
    )

    reports_by_scope: dict[
        str,
        list[SelectOptionDTO],
    ] = field(default_factory=dict)

    details_by_scope: dict[
        str,
        DetailConfigDTO,
    ] = field(default_factory=dict)

    subjects: list[SelectOptionDTO] = field(
        default_factory=list
    )

    all_teachers: list[SelectOptionDTO] = field(
        default_factory=list
    )

    teachers_by_subject: dict[
        str,
        list[SelectOptionDTO],
    ] = field(default_factory=dict)

    primary_teachers: list[SelectOptionDTO] = field(
        default_factory=list
    )


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
