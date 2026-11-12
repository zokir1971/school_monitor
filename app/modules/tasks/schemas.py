# app/modules/tasks/staff_register_schemas.py

from dataclasses import dataclass
from datetime import date


# =========================================================
# REPOSITORY ROW DTOs
# =========================================================

@dataclass(slots=True)
class MyTaskRow:
    """
    Низкоуровневая строка выборки из репозитория.

    Используется только внутри repo/service.
    В шаблон напрямую не передаётся.
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


# =========================================================
# BASE PAGE DTO
# =========================================================

@dataclass(slots=True)
class TaskListBaseDTO:
    """
    Общие данные строки задачи для интерфейса сотрудника.

    Используется как базовый DTO для:
    - ответственного исполнителя;
    - соисполнителя.

    Содержит только общие данные задачи и её отображаемый статус.
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


# =========================================================
# PRIMARY TASK DTO
# =========================================================

@dataclass(slots=True)
class MyTaskDTO(TaskListBaseDTO):
    """
    DTO задачи ответственного исполнителя.

    Используется:
    - в блоке ответственного исполнителя;
    - в верхнем списке страницы исполнения;
    - в сценарии принятия и продолжения задачи.

    Имя MyTaskDTO пока сохраняется, чтобы не ломать существующие
    импорты и маршруты. При итоговой ревизии можно переименовать
    в PrimaryTaskDTO.
    """

    has_selected_reports: bool = False

    action_kind: str = ""
    action_url: str | None = None
    action_label: str | None = None


# =========================================================
# CO-EXECUTOR TASK DTO
# =========================================================

@dataclass(slots=True)
class CoExecutorTaskDTO(TaskListBaseDTO):
    """
    DTO задачи соисполнителя.

    Соисполнитель:
    - не принимает общую задачу;
    - зависит от действий PRIMARY;
    - видит ответственного исполнителя;
    - получает доступ только к назначенным ему отчётам;
    - имеет собственное действие в интерфейсе.
    """

    # PRIMARY
    primary_staff_member_id: int | None = None
    primary_full_name: str = "Не назначен"
    primary_position_text: str | None = None

    # Состояние подготовки задачи
    is_accepted: bool = False
    has_execution_algorithm: bool = False

    # Персональные отчёты соисполнителя
    assigned_reports_count: int = 0
    has_assigned_reports: bool = False
    can_fill_reports: bool = False

    # Действие
    action_kind: str = ""
    action_url: str | None = None
    action_label: str | None = None
    action_css: str | None = None
