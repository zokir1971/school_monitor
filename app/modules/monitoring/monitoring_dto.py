# app/modules/monitoring/monitoring_dto.py

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class StaffTaskScoreDTO:
    """
    Персональный результат одного сотрудника по одной задаче.

    Одна запись соответствует уникальной паре:

        staff_member_id + month_item_id

    Важно:

    - состояние всей задачи хранится отдельно;
    - итоговый документ относится к ответственности PRIMARY;
    - персональные отчёты считаются по
      TaskSelectedReportAssignment;
    - выполненные сотрудником отчёты не обнуляются,
      если вся задача ещё не завершена.
    """

    # =========================================================
    # СОТРУДНИК
    # =========================================================

    user_id: int | None
    staff_member_id: int

    full_name: str
    position_text: str | None

    # =========================================================
    # ЗАДАЧА
    # =========================================================

    month_item_id: int
    month_plan_id: int
    source_row11_id: int | None

    year: int
    month: int
    direction_id: int | None

    # =========================================================
    # РОЛЬ СОТРУДНИКА В ЗАДАЧЕ
    # =========================================================

    assignment_kind: str

    is_primary: bool
    is_co_executor: bool

    # =========================================================
    # СОСТОЯНИЕ ВСЕЙ ЗАДАЧИ
    # =========================================================

    is_completed: bool

    # Итоговый документ относится ко всей задаче,
    # но в персональном рейтинге учитывается только PRIMARY.
    has_final_document: bool

    # =========================================================
    # ПЕРСОНАЛЬНЫЕ НАЗНАЧЕНИЯ ОТЧЁТОВ
    # =========================================================

    assigned_report_count: int
    completed_report_count: int
    pending_report_count: int
    waived_report_count: int

    # =========================================================
    # ПЕРСОНАЛЬНЫЕ ПОКАЗАТЕЛИ
    # =========================================================

    report_completion_percent: float

    # =========================================================
    # БАЛЛЫ
    # =========================================================

    final_document_score: int
    completed_reports_score: int

    total_score: int


@dataclass(slots=True, frozen=True)
class StaffMonitoringRatingDTO:
    """
    Итоговая строка рейтинга одного сотрудника.

    Показатели задачи и личные показатели отчётов
    разделены намеренно.

    Незавершённость общей задачи не должна обнулять
    уже выполненные сотрудником персональные отчёты.
    """

    rank: int

    # =========================================================
    # СОТРУДНИК
    # =========================================================

    user_id: int | None
    staff_member_id: int

    full_name: str
    position_text: str | None

    # =========================================================
    # УЧАСТИЕ В ЗАДАЧАХ
    # =========================================================

    assigned_count: int

    primary_assignment_count: int
    co_executor_assignment_count: int

    # Это состояние всей задачи.
    # Пока сохраняется как отдельный информационный показатель.
    completed_count: int
    not_completed_count: int

    completed_primary_count: int
    completed_co_executor_count: int

    # =========================================================
    # ОТВЕТСТВЕННОСТЬ PRIMARY
    # =========================================================

    final_document_count: int

    # =========================================================
    # ПЕРСОНАЛЬНЫЕ ОТЧЁТЫ
    # =========================================================

    assigned_report_count: int
    completed_report_count: int
    pending_report_count: int
    waived_report_count: int

    report_completion_percent: float

    # =========================================================
    # ИТОГОВЫЕ ПОКАЗАТЕЛИ
    # =========================================================

    total_score: int

    # Пока оставляем процент завершённых задач
    # отдельным показателем состояния участия.
    completion_percent: float

    average_score_per_task: float
    average_score_per_completed_task: float


@dataclass(slots=True, frozen=True)
class StaffMonitoringTotalsDTO:
    """
    Общие показатели рейтинга исполнителей.
    """

    # =========================================================
    # СОТРУДНИКИ И ЗАДАЧИ
    # =========================================================

    staff_count: int = 0

    unique_task_count: int = 0

    # Уникальные задачи, где есть хотя бы один соисполнитель.
    tasks_with_coexecutors_count: int = 0

    # Из них завершено на уровне всей задачи.
    completed_tasks_with_coexecutors_count: int = 0

    # Количество персональных участий:
    # задача + сотрудник.
    assignment_count: int = 0

    # Оставляем как алиас для текущей страницы.
    assigned_count: int = 0

    primary_assignment_count: int = 0
    co_executor_assignment_count: int = 0

    # =========================================================
    # СОСТОЯНИЕ ЗАДАЧ
    # =========================================================

    completed_count: int = 0
    not_completed_count: int = 0

    completed_primary_count: int = 0
    completed_co_executor_count: int = 0

    # =========================================================
    # ОТВЕТСТВЕННОСТЬ PRIMARY
    # =========================================================

    final_document_count: int = 0

    # =========================================================
    # ПЕРСОНАЛЬНЫЕ ОТЧЁТЫ
    # =========================================================

    assigned_report_count: int = 0
    completed_report_count: int = 0
    pending_report_count: int = 0
    waived_report_count: int = 0

    report_completion_percent: float = 0.0

    # =========================================================
    # ИТОГИ
    # =========================================================

    total_score: int = 0

    completion_percent: float = 0.0
    average_score_per_staff: float = 0.0


@dataclass(slots=True, frozen=True)
class StaffMonitoringPageDTO:
    """
    Полный набор данных страницы мониторинга.
    """

    school_plan_id: int
    academic_year: str

    selected_month_plan_id: int | None
    selected_direction_id: int | None

    rating_rows: list[StaffMonitoringRatingDTO] = field(
        default_factory=list
    )

    totals: StaffMonitoringTotalsDTO = field(
        default_factory=StaffMonitoringTotalsDTO
    )
