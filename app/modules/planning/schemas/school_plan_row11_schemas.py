# app/modules/planning/schemas/school_plan_row11_schemas.py
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SchoolPlanRow11OptionDTO:
    value: str
    label: str
    selected: bool = False


@dataclass(slots=True)
class SchoolPlanRow11EditPageDTO:
    # Plan
    plan_id: int
    academic_year: str

    # Direction
    direction_id: int
    direction_name: str

    # Row
    row_id: int
    row_order: int

    topic: str
    goal: str = ""
    control_object: str = ""
    control_type: str = ""
    methods: str = ""

    deadlines: str = ""
    second_control: str = ""

    # Period
    period_type: str = ""
    month: int | None = None
    period_values: str = ""

    # Period UI
    selected_months: list[int] = field(default_factory=list)
    # Template samples
    sample_period_text: str = "—"
    sample_responsibles_text: str = "—"
    sample_review_place_text: str = "—"
    sample_document_text: str = "—"

    # Multi-select
    responsible_roles: list[SchoolPlanRow11OptionDTO] = field(
        default_factory=list
    )
    review_places: list[SchoolPlanRow11OptionDTO] = field(
        default_factory=list
    )
    required_documents: list[SchoolPlanRow11OptionDTO] = field(
        default_factory=list
    )

    content_revision: str = ""

    # State
    is_custom: bool = False
    is_archived: bool = False

    @property
    def can_edit(self) -> bool:
        return not self.is_archived


@dataclass(slots=True)
class SchoolPlanRow11UpdateDTO:
    topic: str
    content_language: str | None = None
    content_revision: str = ""

    goal: str | None = None
    control_object: str | None = None
    control_type: str | None = None
    methods: str | None = None

    deadlines: str | None = None
    second_control: str | None = None

    period_type: str = ""
    month: int | None = None
    period_values: str | None = None

    responsible_roles: list[str] = field(
        default_factory=list
    )

    review_places: list[str] = field(
        default_factory=list
    )

    required_document_types: list[str] = field(
        default_factory=list
    )
