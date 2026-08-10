# app/modules/reports/schemas/report_assignment_dto.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ReportAssignmentExecutorDTO:
    """
    Допустимый исполнитель выбранного отчёта.

    В список входят только сотрудники, назначенные
    на текущую задачу как:

    - ответственный исполнитель PRIMARY;
    - соисполнитель CO_EXECUTOR.
    """

    staff_member_id: int
    full_name: str

    assignment_kind: str
    assignment_kind_label: str

    position_text: str | None = None

    is_primary: bool = False
    is_co_executor: bool = False


@dataclass(frozen=True, slots=True)
class ReportAssignmentRowDTO:
    """
    Один выбранный системный отчёт на странице распределения.
    Строка содержит:
    - описание выбранного отчёта;
    - текущего исполнителя;
    - состояние назначения;
    - сведения об освобождении от выполнения отчёта.
    Assignment_status:
        pending отчёт назначен и ожидает выполнения;
        completed отчёт выполнен;
        waived ответственный разрешил завершить задачу без данного отчёта.
    """

    selected_report_id: int

    report_type_id: int
    report_code: str
    report_name: str

    target_kind: str
    target_value: str
    target_label: str

    # =========================================================
    # ТЕКУЩЕЕ НАЗНАЧЕНИЕ
    # =========================================================

    assigned_staff_member_id: int | None = None
    assigned_staff_full_name: str | None = None

    assigned_at: datetime | None = None
    assigned_by_user_id: int | None = None

    # =========================================================
    # СОСТОЯНИЕ НАЗНАЧЕНИЯ
    # =========================================================

    assignment_status: str | None = None
    assignment_status_label: str | None = None

    # =========================================================
    # ОСВОБОЖДЕНИЕ ОТ ОТЧЁТА
    # =========================================================

    waived_reason: str | None = None
    waived_by_user_id: int | None = None
    waived_at: datetime | None = None

    # =========================================================
    # HELPERS
    # =========================================================

    @property
    def is_assigned(self) -> bool:
        """
        Назначен ли отчёту исполнитель.
        """
        return self.assigned_staff_member_id is not None

    @property
    def is_pending(self) -> bool:
        """
        Отчёт ожидает выполнения.
        """
        return self.assignment_status == "pending"

    @property
    def is_completed(self) -> bool:
        """
        Отчёт выполнен.
        """
        return self.assignment_status == "completed"

    @property
    def is_waived(self) -> bool:
        """
        Отчёт официально освобождён от выполнения.
        """
        return self.assignment_status == "waived"

    @property
    def is_resolved(self) -> bool:
        """
        Назначение больше не блокирует завершение задачи.

        Завершённым считается:

        - выполненный отчёт;
        - отчёт, от которого ответственный
          официально освободил исполнителя.
        """
        return self.assignment_status in {
            "completed",
            "waived",
        }


@dataclass(slots=True)
class ReportAssignmentPageDTO:
    """
    DTO страницы распределения выбранных отчётов.

    Формируется для ответственного исполнителя после того,
    как он составил алгоритм выполнения и выбрал системные
    отчёты.
    """

    month_item_id: int
    month: int

    task_topic: str = "—"
    task_goal: str = "—"
    period_text: str = "—"

    executors: list[ReportAssignmentExecutorDTO] = field(
        default_factory=list
    )

    reports: list[ReportAssignmentRowDTO] = field(
        default_factory=list
    )

    @property
    def report_count(self) -> int:
        """
        Общее количество выбранных отчётов.
        """
        return len(self.reports)

    @property
    def assigned_count(self) -> int:
        """
        Количество отчётов, которым назначен исполнитель.
        """
        return sum(
            1
            for report in self.reports
            if report.is_assigned
        )

    @property
    def unassigned_count(self) -> int:
        """
        Количество отчётов без исполнителя.
        """
        return self.report_count - self.assigned_count

    @property
    def all_assigned(self) -> bool:
        """
        Все ли выбранные отчёты распределены.

        Если отчётов нет, возвращается False.
        """
        if self.report_count == 0:
            return False

        return self.assigned_count == self.report_count

    @property
    def pending_count(self) -> int:
        """
        Количество отчётов,
        которые ещё ожидают выполнения.
        """
        return sum(
            1
            for report in self.reports
            if report.is_pending
        )

    @property
    def completed_count(self) -> int:
        """
        Количество выполненных отчётов.
        """
        return sum(
            1
            for report in self.reports
            if report.is_completed
        )

    @property
    def waived_count(self) -> int:
        """
        Количество отчётов,
        освобождённых от обязательного выполнения.
        """
        return sum(
            1
            for report in self.reports
            if report.is_waived
        )

    @property
    def all_resolved(self) -> bool:
        """
        Все ли назначенные отчёты закрыты.

        Закрытый отчёт:

        - COMPLETED;
        - WAIVED.

        Если отчётов нет, возвращается False.
        """
        if self.report_count == 0:
            return False

        return all(
            report.is_resolved
            for report in self.reports
        )


@dataclass(frozen=True, slots=True)
class ReportAssignmentInputDTO:
    """
    Одна строка данных, полученная из формы распределения.

    Сервис обязан дополнительно проверить:

    - отчёт относится к выбранной задаче;
    - сотрудник назначен на эту задачу;
    - текущий пользователь является PRIMARY;
    - выбранный отчёт ещё можно переназначать.
    """

    selected_report_id: int
    staff_member_id: int


@dataclass(frozen=True, slots=True)
class ReportAssignmentSaveResultDTO:
    """
    Результат сохранения распределения отчётов.
    """

    month_item_id: int

    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    deleted_count: int = 0

    @property
    def changed_count(self) -> int:
        """
        Общее количество изменённых назначений.
        """
        return (
            self.created_count
            + self.updated_count
            + self.deleted_count
        )
