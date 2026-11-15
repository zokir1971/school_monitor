# app/modules/planning/schemas/month_plan_page_schemas.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class MonthPlanAssignmentSummaryDTO:
    """
    Краткая сводка назначений задачи месячного плана.

    Используется репозиторием и сервисом страницы месячного плана.
    ORM-модели сотрудников и должностных ролей наружу не передаются.
    """

    has_primary_assignee: bool
    primary_assignee_name: str | None
    co_executor_count: int

    co_executor_names: list[str] = field(
        default_factory=list
    )


@dataclass(slots=True)
class MonthPlanItemRowDTO:
    """
    Строка таблицы месячного плана.

    DTO содержит только данные, необходимые странице.
    Он не зависит от SQLAlchemy и не меняет бизнес-логику
    формирования, сохранения или отправки месячного плана.
    """

    # -----------------------------------------------------
    # Идентификаторы
    # -----------------------------------------------------
    id: int
    source_row11_id: int | None

    # -----------------------------------------------------
    # Состояние строки месячного плана
    # -----------------------------------------------------
    is_included: bool
    week_of_month: int | None

    planned_start: date | None
    planned_end: date | None

    notes: str | None

    status: str
    status_label: str

    # -----------------------------------------------------
    # Данные исходной строки годового плана
    # -----------------------------------------------------
    topic: str
    goal: str
    control_object: str
    methods: str
    deadlines: str

    period_type: str
    period_value_int: int | None
    period_values: str | None

    # -----------------------------------------------------
    # Направление
    # -----------------------------------------------------
    direction_id: int
    direction_name: str

    # -----------------------------------------------------
    # Состояние назначения
    # -----------------------------------------------------
    has_primary_assignee: bool
    co_executor_count: int

    # -----------------------------------------------------
    # Исполнители
    # -----------------------------------------------------
    schedule_warning: bool = False

    primary_assignee_name: str | None = None

    co_executor_names: list[str] = field(
        default_factory=list
    )

    # -----------------------------------------------------
    # Готовые подписи мест рассмотрения
    # -----------------------------------------------------
    review_place_labels: list[str] = field(
        default_factory=list
    )

    @property
    def is_assigned(self) -> bool:
        """
        Задача считается назначенной только при наличии
        основного исполнителя.
        """

        return self.has_primary_assignee

    @property
    def assignment_label(self) -> str:
        """
        Подпись кнопки назначения.
        """

        if not self.has_primary_assignee:
            return "Назначить"

        if self.co_executor_count > 0:
            return f"Назначено (+{self.co_executor_count})"

        return "Назначено"


@dataclass(slots=True)
class MonthPlanDirectionBlockDTO:
    """
    Группа строк месячного плана одного направления ВШК.
    """

    direction_id: int
    direction_name: str
    sort_order: int = 9999

    items: list[MonthPlanItemRowDTO] = field(
        default_factory=list
    )
