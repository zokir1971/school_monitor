# app/modules/reviews/review_result_dto.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.modules.planning.enums import ReviewPlace


@dataclass(slots=True, frozen=True)
class ReviewResultAccessDTO:
    """
    Контекст доступа текущего пользователя.

    Для администратора participant_user_id и
    participant_staff_id равны None.

    Для сотрудника содержат идентификаторы,
    необходимые репозиторию для ограничения выборки.
    """

    school_id: int
    is_admin: bool

    participant_user_id: int | None
    participant_staff_id: int | None


@dataclass(slots=True, frozen=True)
class ReviewResultDocumentDTO:
    """
    Документ, доступный для просмотра и скачивания.
    """

    document_id: int

    title: str
    file_name: str | None
    file_path: str

    view_url: str
    download_url: str


@dataclass(slots=True, frozen=True)
class ReviewResultListItemDTO:
    """
    Одна строка таблицы результатов рассмотрения.
    """

    month_item_id: int

    task_name: str
    task_goal: str | None

    responsible_name: str | None
    participation_label: str | None

    year: int
    month: int
    week_of_month: int | None

    planned_start: date | None
    planned_end: date | None
    planned_period_text: str

    task_status: str
    task_status_label: str

    review_place: str
    review_place_label: str

    is_reviewed: bool
    review_count: int

    latest_review_result_id: int | None
    latest_review_status: str | None
    latest_review_status_label: str | None
    latest_reviewed_at: datetime | None
    latest_review_comment: str | None

    latest_protocol_number: str | None
    latest_protocol_date: date | None


@dataclass(slots=True, frozen=True)
class ReviewResultHistoryItemDTO:
    """
    Один результат в истории рассмотрений задачи.
    """

    review_result_id: int

    review_place: str
    review_place_label: str

    status: str
    status_label: str

    reviewed_at: datetime | None
    created_at: datetime

    reviewed_by_name: str | None

    comment: str | None

    protocol_document_id: int | None
    has_protocol_document: bool

    protocol_number: str | None
    protocol_date: date | None

    protocol_document: ReviewResultDocumentDTO | None


@dataclass(slots=True, frozen=True)
class ReviewResultListPageDTO:
    """
    Полные данные страницы списка результатов.
    """

    school_plan_id: int
    school_id: int

    academic_year_label: str

    is_admin: bool

    selected_year: int | None
    selected_month: int | None
    selected_review_place: ReviewPlace | None
    selected_reviewed: bool | None
    selected_task_review_id: int | None

    available_years: list[int]
    available_months: list[dict[str, int | str]]
    review_places: list[dict[str, str]]
    available_protocols: list[dict[str, int | str]]

    items: list[ReviewResultListItemDTO]

    total_count: int
    reviewed_count: int
    not_reviewed_count: int


@dataclass(slots=True, frozen=True)
class ReviewResultTaskDetailDTO:
    """
    Детальная информация по одной задаче.
    """

    month_item_id: int

    task_name: str
    task_goal: str | None
    responsibles_text: str | None

    responsible_name: str | None
    participation_label: str | None

    year: int
    month: int
    week_of_month: int | None

    planned_start: date | None
    planned_end: date | None
    planned_period_text: str

    executed_at: date | None

    task_status: str
    task_status_label: str

    notes: str | None

    review_place: ReviewPlace | None
    review_place_label: str | None

    history: list[ReviewResultHistoryItemDTO]
    review_count: int

    final_document: ReviewResultDocumentDTO | None
    execution_reports: list[ReviewResultDocumentDTO]
