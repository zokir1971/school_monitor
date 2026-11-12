# app/modules/planning/month_plan_assignee_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class AssigneeOptionDTO:
    """
    Конкретная должностная роль сотрудника, доступная
    для назначения на задачу месячного плана.

    Важно:
    назначение сохраняется по staff_role_id,
    а не непосредственно по staff_member_id.
    """

    staff_role_id: int
    staff_member_id: int

    full_name: str
    role: str
    role_label: str

    role_context: str = ""
    position_text: str = ""
    subject: str = ""

    selected_as_primary: bool = False
    selected_as_co_executor: bool = False


@dataclass(slots=True)
class AssigneeGroupDTO:
    """
    Группа кандидатов по должностной роли или категории.
    """

    code: str
    label: str

    role_context: str = ""

    options: list[AssigneeOptionDTO] = field(
        default_factory=list
    )


@dataclass(slots=True)
class AssignedParticipantDTO:
    """
    Уже назначенный участник задачи.
    """

    staff_role_id: int
    staff_member_id: int

    full_name: str
    role_label: str
    assignment_kind: str
    assignment_kind_label: str

    role_context: str = ""
    position_text: str = ""


@dataclass(slots=True)
class MonthItemAssigneePageDTO:
    """
    Полный контракт страницы назначения исполнителей.
    """

    month_item_id: int
    row11_id: int | None = None

    direction_name: str = "—"
    topic: str = "—"
    goal: str = "—"

    week_of_month: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None

    is_included: bool = False
    can_assign: bool = False

    primary_groups: list[AssigneeGroupDTO] = field(
        default_factory=list
    )

    planned_co_executor_groups: list[AssigneeGroupDTO] = field(
        default_factory=list
    )

    additional_co_executor_groups: list[AssigneeGroupDTO] = field(
        default_factory=list
    )

    assigned_participants: list[AssignedParticipantDTO] = field(
        default_factory=list
    )

    selected_primary_staff_role_id: int | None = None

    selected_co_executor_staff_role_ids: list[int] = field(
        default_factory=list
    )

    month: int | None = None
    school_plan_id: int | None = None
    is_active_plan: bool = False
    year: int | None = None
    plan_revision: str = ""
