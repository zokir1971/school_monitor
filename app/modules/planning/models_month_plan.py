# app/modules/planning/models_month_plan.py

from __future__ import annotations

from datetime import datetime, date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func)
from sqlalchemy import Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import PLAN_STATUS_ENUM, PLAN_ITEM_STATUS_ENUM, RESPONSIBLE_ROLE_ENUM, REVIEW_PLACE_ENUM, \
    ASSIGNMENT_KIND_ENUM
from app.modules.planning.enums import PlanItemStatus, PlanStatus, ResponsibleRole, ReviewPlace, AssignmentKind

if TYPE_CHECKING:
    from app.modules.planning.models_school import SchoolPlanRow11, SchoolPlan
    from app.modules.staff.models_staff_school import SchoolStaffRole
    from app.modules.users.models import User


class SchoolMonthPlan(Base):
    __tablename__ = "school_month_plans"
    __table_args__ = (
        UniqueConstraint(
            "school_plan_id",
            "year",
            "month",
            name="uq_school_month_plan_school_plan_year_month",
        ),
        Index(
            "ix_school_month_plans_plan_year_month_status",
            "school_plan_id",
            "year",
            "month",
            "status"
        ),
        CheckConstraint(
            "(month BETWEEN 9 AND 12) OR (month BETWEEN 1 AND 5)",
            name="ck_school_month_plans_month_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    school_plan_id: Mapped[int] = mapped_column(
        ForeignKey("school_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # год для календаря
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # 9..12, 1..5 (сентябрь–май)
    month: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    status: Mapped[PlanStatus] = mapped_column(
        PLAN_STATUS_ENUM,  # общий enum из app/db/types.py
        nullable=False,
        default=PlanStatus.DRAFT,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # relationships
    school_plan: Mapped["SchoolPlan"] = relationship(
        "SchoolPlan",
        back_populates="month_plans",
        lazy="selectin",
    )

    items: Mapped[list["SchoolMonthPlanItem"]] = relationship(
        "SchoolMonthPlanItem",
        back_populates="month_plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SchoolMonthPlanItem.id.asc()",
        lazy="selectin",
    )


class SchoolMonthPlanItem(Base):
    __tablename__ = "school_month_plan_items"
    __table_args__ = (
        UniqueConstraint("month_plan_id", "source_row11_id", name="uq_month_plan_item_unique_source"),
        CheckConstraint(
            "week_of_month IS NULL OR (week_of_month >= 1 AND week_of_month <= 6)",
            name="ck_month_plan_item_week_range",
        ),
        CheckConstraint(
            "planned_end IS NULL OR planned_start IS NULL OR planned_end >= planned_start",
            name="ck_month_plan_item_date_range",
        ),
        Index("ix_month_plan_items_plan_included_week", "month_plan_id", "is_included", "week_of_month"),
        Index("ix_month_plan_items_source_status", "source_row11_id", "status"),
        Index("ix_month_plan_items_plan_dates", "month_plan_id", "planned_start", "planned_end")
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    month_plan_id: Mapped[int] = mapped_column(
        ForeignKey("school_month_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Идеально: если в годовом плане строку удалили — item не умирает, а просто теряет ссылку
    source_row11_id: Mapped[int | None] = mapped_column(
        ForeignKey("school_plan_rows_11.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    # обязательна для включённых задач (проверим в сервисе при переводе DRAFT->ACTIVE)
    week_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    status: Mapped[PlanItemStatus] = mapped_column(
        PLAN_ITEM_STATUS_ENUM,  # ✅ общий enum из app/db/types.py
        nullable=False,
        default=PlanItemStatus.TODO,
        index=True,
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Ответственные (роль + конкретный пользователь)
    responsible_role: Mapped[ResponsibleRole | None] = mapped_column(
        RESPONSIBLE_ROLE_ENUM,  # ✅ общий enum из app/db/types.py
        nullable=True,
        index=True,
    )

    responsible_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # недели
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # relationships
    month_plan: Mapped["SchoolMonthPlan"] = relationship(
        "SchoolMonthPlan",
        back_populates="items",
        lazy="selectin",
    )

    source_row11: Mapped[SchoolPlanRow11 | None] = relationship(
        "SchoolPlanRow11",
        back_populates="month_items",
        foreign_keys=[source_row11_id],
        lazy="selectin",
    )

    responsible_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[responsible_user_id],
        lazy="selectin",
    )

    review_places: Mapped[list["SchoolMonthPlanItemReviewPlace"]] = relationship(
        "SchoolMonthPlanItemReviewPlace",
        back_populates="month_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    assignees: Mapped[list["SchoolMonthPlanItemAssignee"]] = relationship(
        "SchoolMonthPlanItemAssignee",
        back_populates="month_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class SchoolMonthPlanItemAssignee(Base):
    __tablename__ = "school_month_plan_item_assignees"

    __table_args__ = (
        UniqueConstraint(
            "month_item_id",
            "staff_role_id",
            name="uq_month_item_assignee_role",
        ),
        Index("ix_month_item_assignee_staff_role", "staff_role_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    month_item_id: Mapped[int] = mapped_column(
        ForeignKey("school_month_plan_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    staff_role_id: Mapped[int] = mapped_column(
        ForeignKey("school_staff_roles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    assignment_kind: Mapped[AssignmentKind] = mapped_column(
        ASSIGNMENT_KIND_ENUM,
        nullable=False,
        index=True,
    )

    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    month_item: Mapped["SchoolMonthPlanItem"] = relationship(
        "SchoolMonthPlanItem",
        back_populates="assignees",
        lazy="selectin",
    )

    staff_role: Mapped["SchoolStaffRole"] = relationship(
        "SchoolStaffRole",
        lazy="selectin",
    )


class SchoolMonthPlanItemReviewPlace(Base):
    __tablename__ = "school_month_plan_item_review_places"
    __table_args__ = (
        UniqueConstraint("month_item_id", "review_place", name="uq_month_item_review_place"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    month_item_id: Mapped[int] = mapped_column(
        ForeignKey("school_month_plan_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    review_place: Mapped[ReviewPlace] = mapped_column(
        REVIEW_PLACE_ENUM,
        nullable=False,
        index=True,
    )

    month_item: Mapped["SchoolMonthPlanItem"] = relationship(
        "SchoolMonthPlanItem",
        back_populates="review_places",
    )
