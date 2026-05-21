# app/modules/staff/report_schemas.py

from dataclasses import dataclass
from datetime import date


# =========================
# BASE TASK DTOs
# =========================
@dataclass(slots=True)
class MyTaskRow:
    """
    Низкоуровневая строка выборки из repo.
    Используется внутри repo/service, в шаблон напрямую не передается.
    """
    month_item_id: int
    week_of_month: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None

    topic: str | None = None
    goal: str | None = None
    control_object: str | None = None
    control_type: str | None = None
    review_place: str | None = None

    status: object | str | None = None

    has_selected_reports: bool = False


@dataclass(slots=True)
class MyTaskDTO:
    """
    DTO для списка задач.
    Подходит для:
    - school_staff_task.html
    - верхнего списка задач в task_execute.html
    """
    month_item_id: int
    week_of_month: int | None = None
    planned_start: date | None = None
    planned_end: date | None = None

    period_text: str = "—"

    topic: str = "—"
    goal: str = "—"
    control_object: str = "—"
    control_type: str = "—"
    review_place: str = "—"

    status: str = ""
    status_label: str = ""
    status_color: str = ""

    has_selected_reports: bool = False

    action_kind: str = ""
    action_url: str | None = None
    action_label: str | None = None
