from dataclasses import dataclass
from datetime import date


@dataclass
class MyTaskDTO:
    month_item_id: int
    week_of_month: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None
    topic: str | None = None
    goal: str | None = None
    control_object: str | None = None
    control_type: str | None = None
    review_place: str | None = None
    status: str = ""
    status_label: str = ""


@dataclass
class StaffExecutionTaskDTO:
    month_item_id: int
    week_of_month: int | None
    planned_start: date | None
    planned_end: date | None
    topic: str | None
    goal: str | None
    control_object: str | None
    control_type: str | None
    control_form: str | None
    review_place: str
    status: str
    status_label: str
