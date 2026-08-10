# app/modules/reports/models_report_assignments.py
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func, Integer,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import REPORT_ASSIGNMENT_STATUS_ENUM
from app.modules.reports.enums import ReportAssignmentStatus

if TYPE_CHECKING:
    from app.modules.reports.models_documents import (
        TaskExecutionSelectedReport,
    )
    from app.modules.staff.models_staff_school import (
        SchoolStaffMember,
    )
    from app.modules.users.models import User


class TaskSelectedReportAssignment(Base):
    """
    Назначение конкретного выбранного отчёта
    конкретному исполнителю задачи.

    Один выбранный отчёт назначается одному сотруднику.

    Статус назначения показывает,
    требуется ли ещё выполнение отчёта:

        PENDING
            отчёт ожидает выполнения;

        COMPLETED
            отчёт выполнен;

        WAIVED
            ответственный разрешил завершить
            задачу без данного отчёта.

    Переназначение отчёта другому сотруднику
    не изменяет статус: он остаётся PENDING.
    """

    __tablename__ = "task_selected_report_assignments"

    __table_args__ = (
        UniqueConstraint(
            "selected_report_id",
            name=(
                "uq_task_selected_report_assignments_"
                "selected_report_id"
            ),
        ),

        Index(
            "ix_task_selected_report_assignments_"
            "staff_member_id",
            "staff_member_id",
        ),

        Index(
            "ix_task_selected_report_assignments_"
            "assigned_by_user_id",
            "assigned_by_user_id",
        ),

        Index(
            "ix_task_selected_report_assignments_status",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    # =========================================================
    # ВЫБРАННЫЙ ОТЧЁТ
    # =========================================================

    selected_report_id: Mapped[int] = mapped_column(
        ForeignKey(
            "task_execution_selected_reports.id",
            name=(
                "fk_task_selected_report_assignments_"
                "selected_report_id"
            ),
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # =========================================================
    # ТЕКУЩИЙ ИСПОЛНИТЕЛЬ ОТЧЁТА
    # =========================================================

    staff_member_id: Mapped[int] = mapped_column(
        ForeignKey(
            "school_staff_members.id",
            name=(
                "fk_task_selected_report_assignments_"
                "staff_member_id"
            ),
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    # =========================================================
    # НАЗНАЧЕНИЕ
    # =========================================================

    assigned_by_user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            name=(
                "fk_task_selected_report_assignments_"
                "assigned_by_user_id"
            ),
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # =========================================================
    # СОСТОЯНИЕ ОБЯЗАННОСТИ ПО ОТЧЁТУ
    # =========================================================

    status: Mapped[ReportAssignmentStatus] = mapped_column(
        REPORT_ASSIGNMENT_STATUS_ENUM,
        nullable=False,
        default=ReportAssignmentStatus.PENDING,
        server_default=ReportAssignmentStatus.PENDING.value,
    )

    # =========================================================
    # ОСВОБОЖДЕНИЕ ОТ ОТЧЁТА
    # =========================================================

    waived_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    waived_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            name=(
                "fk_task_selected_report_assignments_"
                "waived_by_user_id"
            ),
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    waived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # =========================================================
    # СЛУЖЕБНЫЕ ПОЛЯ
    # =========================================================

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =========================================================
    # RELATIONSHIPS
    # =========================================================

    selected_report: Mapped[
        TaskExecutionSelectedReport
    ] = relationship(
        "TaskExecutionSelectedReport",
        back_populates="executor_assignment",
        lazy="raise",
    )

    staff_member: Mapped[
        SchoolStaffMember
    ] = relationship(
        "SchoolStaffMember",
        back_populates="selected_report_assignments",
        foreign_keys=[staff_member_id],
        lazy="raise",
    )

    assigned_by_user: Mapped[
        User
    ] = relationship(
        "User",
        foreign_keys=[assigned_by_user_id],
        lazy="raise",
    )

    waived_by_user: Mapped[
        User | None
    ] = relationship(
        "User",
        foreign_keys=[waived_by_user_id],
        lazy="raise",
    )
