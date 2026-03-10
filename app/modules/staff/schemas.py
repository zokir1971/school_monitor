
from dataclasses import dataclass
from datetime import date


@dataclass
class MyTaskDTO:
    month_item_id: int
    week_of_month: int | None
    planned_start: date | None
    planned_end: date | None

    topic: str | None
    goal: str | None
    control_object: str | None
    control_type: str | None
    review_place: str | None
