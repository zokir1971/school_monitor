# app/modules/planning/models_month_plan_notification.py

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import MONTH_PLAN_NOTIFICATION_STATUS_ENUM
from app.modules.planning.enums import MonthPlanNotificationStatus

if TYPE_CHECKING:
    from app.modules.planning.models_month_plan import (
        SchoolMonthPlan,
    )
    from app.modules.staff.models_staff_school import (
        SchoolStaffMember,
    )
    from app.modules.users.models import User


class SchoolMonthPlanNotification(Base):
    """
    Текущее состояние WhatsApp-уведомления исполнителя
    по месячному плану.

    Для одной пары «месячный план + сотрудник» хранится
    одна запись. Повторные открытия WhatsApp увеличивают
    open_count и обновляют последнее состояние.
    """

    __tablename__ = "school_month_plan_notifications"

    __table_args__ = (
        UniqueConstraint(
            "month_plan_id",
            "staff_member_id",
            name="uq_month_plan_notification_plan_staff",
        ),
        CheckConstraint(
            "open_count >= 0",
            name="ck_month_plan_notification_open_count",
        ),
        Index(
            "ix_month_plan_notification_plan_status",
            "month_plan_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    month_plan_id: Mapped[int] = mapped_column(
        ForeignKey(
            "school_month_plans.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey(
            "school_staff_members.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # Последний номер, для которого формировалась ссылка.
    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    status: Mapped[MonthPlanNotificationStatus] = mapped_column(
        MONTH_PLAN_NOTIFICATION_STATUS_ENUM,
        nullable=False,
        default=MonthPlanNotificationStatus.PENDING,
    )

    # Последний сформированный текст сообщения.
    message_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Количество открытий ссылки WhatsApp.
    open_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    opened_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    opened_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    confirmed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    month_plan: Mapped[SchoolMonthPlan] = relationship(
        "SchoolMonthPlan",
        lazy="selectin",
    )

    staff_member: Mapped[SchoolStaffMember] = relationship(
        "SchoolStaffMember",
        lazy="selectin",
    )

    opened_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[opened_by_user_id],
        lazy="selectin",
    )

    confirmed_by: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[confirmed_by_user_id],
        lazy="selectin",
    )
