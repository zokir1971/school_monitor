# app/modules/tasks/task_review_dto.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date

from app.modules.planning.enums import ReviewPlace, PlanItemStatus


@dataclass(slots=True)
class TaskReviewCreateDTO:
    """
    Данные для создания результата рассмотрения одной задачи.

    Поле status рассчитывается сервисом:

        DONE         -> REVIEWED
        NOT_EXECUTED -> NOT_EXECUTED
    """

    month_item_id: int
    task_review_id: int
    reviewed_by_user_id: int
    review_place: ReviewPlace
    status: PlanItemStatus
    protocol_document_id: int | None
    reviewed_at: datetime
    comment: str | None = None


@dataclass(slots=True)
class TaskReviewReadDTO:
    """
    Данные результата рассмотрения для чтения.
    """

    id: int
    month_item_id: int
    review_place: ReviewPlace
    reviewed_by_user_id: int
    protocol_document_id: int | None
    comment: str | None
    created_at: datetime
    updated_at: datetime | None


@dataclass(slots=True)
class TaskReviewSelectionItemDTO:
    """
    Одна строка таблицы выбора задач для рассмотрения.
    """

    month_item_id: int

    task_name: str
    responsible_name: str

    planned_start: date | None
    planned_end: date | None
    planned_period_text: str

    status: str
    status_label: str

    can_select: bool
    has_review_result: bool
    expected_result_label: str


@dataclass(slots=True)
class MethodAssociationSelectionItemDTO:
    """
    Один пункт списка методических объединений.
    """

    id: int
    name: str


@dataclass(slots=True)
class TaskReviewSelectionPageDTO:
    """
    Данные страницы выбора задач для рассмотрения.
    """

    school_plan_id: int
    academic_year_label: str

    selected_review_place: ReviewPlace | None
    selected_method_association_id: int | None

    review_places: list[ReviewPlace]
    method_associations: list[MethodAssociationSelectionItemDTO]

    tasks: list[TaskReviewSelectionItemDTO]
    overdue_tasks: list[TaskReviewSelectionItemDTO]


@dataclass(slots=True)
class TaskReviewBatchCreateDTO:
    """
    Общие данные одной атомарной операции рассмотрения задач.

    Один протокол и одно место рассмотрения применяются
    ко всем выбранным задачам. SchoolTaskReview создаётся
    сервисом внутри той же транзакции, что и результаты.
    """

    month_item_ids: list[int]
    review_place: ReviewPlace
    reviewed_by_user_id: int

    protocol_number: str
    protocol_date: date

    method_association_id: int | None = None
    comment: str | None = None
