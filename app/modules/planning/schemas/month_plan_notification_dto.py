# app/modules/planning/schemas/month_plan_notification_dto.py

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from app.modules.planning.enums import MonthPlanNotificationStatus


@dataclass(frozen=True, slots=True)
class MonthPlanNotificationAssignmentRowDTO:
    """
    Плоская строка назначения, возвращаемая репозиторием.

    Репозиторий не группирует данные по сотрудникам и не создаёт
    вложенные структуры получателей уведомлений.
    """

    staff_member_id: int
    full_name: str
    phone: str | None
    is_registered: bool

    assignment_kind: str

    month_item_id: int
    task_title: str
    planned_start: date | None
    planned_end: date | None
    user_id: int | None = None
    is_account_active: bool = False


@dataclass(frozen=True, slots=True)
class MonthPlanNotificationTaskDTO:
    """
    Одна задача в уведомлении исполнителя.
    """

    month_item_id: int
    title: str
    planned_start: date | None
    planned_end: date | None

    @property
    def deadline_text(self) -> str:
        if self.planned_start and self.planned_end:
            if self.planned_start == self.planned_end:
                return self.planned_start.strftime("%d.%m.%Y")

            return (
                f"{self.planned_start:%d.%m.%Y} – "
                f"{self.planned_end:%d.%m.%Y}"
            )

        if self.planned_start:
            return f"с {self.planned_start:%d.%m.%Y}"

        if self.planned_end:
            return f"до {self.planned_end:%d.%m.%Y}"

        return "Срок не указан"


@dataclass(slots=True)
class MonthPlanNotificationRecipientDTO:
    """
    Получатель уведомления по задачам месячного плана.

    Один сотрудник представлен одной строкой независимо
    от количества назначенных ему задач.
    """

    staff_member_id: int
    full_name: str
    is_registered: bool

    phone: str | None = None
    user_id: int | None = None

    primary_tasks: list[MonthPlanNotificationTaskDTO] = field(
        default_factory=list
    )

    co_executor_tasks: list[MonthPlanNotificationTaskDTO] = field(
        default_factory=list
    )

    @property
    def task_count(self) -> int:
        return (
                len(self.primary_tasks)
                + len(self.co_executor_tasks)
        )

    @property
    def role_summary(self) -> str:
        has_primary = bool(self.primary_tasks)
        has_co_executor = bool(self.co_executor_tasks)

        if has_primary and has_co_executor:
            return "Ответственный и соисполнитель"

        if has_primary:
            return "Ответственный"

        if has_co_executor:
            return "Соисполнитель"

        return "Исполнитель"


@dataclass(frozen=True, slots=True)
class MonthPlanNotificationStatusDTO:
    """
    Состояние уведомления исполнителя
    по месячному плану.
    """

    staff_member_id: int
    full_name: str
    phone: str | None

    is_registered: bool

    status: MonthPlanNotificationStatus

    open_count: int

    opened_at: datetime | None

    confirmed_at: datetime | None


@dataclass(frozen=True, slots=True)
class MonthPlanNotificationProgressDTO:
    """
    Сводное состояние уведомлений исполнителей
    месячного плана.
    """

    total_recipients: int

    pending_count: int
    sent_count: int
    accepted_count: int

    @property
    def all_sent(self) -> bool:
        """
        Всем исполнителям отправлены уведомления.

        Статус ACCEPTED также считается отправленным,
        поскольку принятие задачи происходит после отправки.
        """
        if self.total_recipients == 0:
            return False

        sent_total = (
            self.sent_count
            + self.accepted_count
        )

        return sent_total >= self.total_recipients

    @property
    def sent_total(self) -> int:
        """
        Количество исполнителей, которым уведомление
        отправлено либо которые уже приняли задачу.
        """
        return (
            self.sent_count
            + self.accepted_count
        )

    @property
    def sent_percent(self) -> int:
        """
        Процент отправленных уведомлений.
        """
        if self.total_recipients == 0:
            return 0

        return round(
            self.sent_total
            * 100
            / self.total_recipients
        )

    @property
    def accepted_percent(self) -> int:
        """
        Процент исполнителей, принявших задачу.
        """
        if self.total_recipients == 0:
            return 0

        return round(
            self.accepted_count
            * 100
            / self.total_recipients
        )
