# app/modules/task/models_task_review.py
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import PLAN_ITEM_STATUS_ENUM, REVIEW_PLACE_ENUM
from app.modules.planning.enums import PlanItemStatus, ReviewPlace

if TYPE_CHECKING:
    from app.modules.planning.models import SchoolPlan
    from app.modules.planning.models_month_plan import SchoolMonthPlanItem
    from app.modules.reports.models_documents import TaskExecutionDocument
    from app.modules.users.models import User


class SchoolMethodAssociation(Base):
    """
    Конкретное методическое объединение школы.
    """

    __tablename__ = "school_method_associations"

    __table_args__ = (
        UniqueConstraint(
            "school_id",
            "name",
            name="uq_school_method_association_school_name",
        ),
        UniqueConstraint(
            "school_id",
            "code",
            name="uq_school_method_association_school_code",
        ),
        Index(
            "ix_school_method_associations_active_school_name",
            "school_id",
            "name",
            postgresql_where=text("is_active IS TRUE"),
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
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

    task_reviews: Mapped[list["SchoolTaskReview"]] = relationship(
        "SchoolTaskReview",
        back_populates="method_association",
        lazy="raise",
    )


class SchoolTaskReview(Base):
    """
    Одно пакетное рассмотрение задач ВШК.

    Одна запись соответствует одному заседанию,
    одному конкретному протоколу и, при необходимости,
    одному конкретному методическому объединению.
    """

    __tablename__ = "school_task_reviews"

    __table_args__ = (
        # Основная выборка рассмотрений плана.
        Index(
            "ix_school_task_reviews_plan_place_date",
            "school_plan_id",
            "review_place",
            "protocol_date",
        ),

        # История рассмотрений конкретного МО.
        Index(
            "ix_school_task_reviews_method_assoc_protocol_date",
            "method_association_id",
            "protocol_date",
        ),

        # Один протокол для обычного места рассмотрения.
        #
        # method_association_id здесь всегда NULL.
        Index(
            "uq_school_task_reviews_protocol_identity_general",
            "school_plan_id",
            "review_place",
            "protocol_number",
            "protocol_date",
            unique=True,
            postgresql_where=text(
                "method_association_id IS NULL"
            ),
        ),

        # Один протокол для конкретного методического объединения.
        Index(
            "uq_school_task_reviews_protocol_identity_method_assoc",
            "school_plan_id",
            "review_place",
            "method_association_id",
            "protocol_number",
            "protocol_date",
            unique=True,
            postgresql_where=text(
                "method_association_id IS NOT NULL"
            ),
        ),

        CheckConstraint(
            """
            (
                review_place = 'method_assoc'
                AND method_association_id IS NOT NULL
            )
            OR
            (
                review_place <> 'method_assoc'
                AND method_association_id IS NULL
            )
            """,
            name="ck_school_task_review_method_association",
        ),

        CheckConstraint(
            "btrim(protocol_number) <> ''",
            name="ck_school_task_reviews_protocol_number_not_blank",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    school_plan_id: Mapped[int] = mapped_column(
        ForeignKey(
            "school_plans.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    review_place: Mapped[ReviewPlace] = mapped_column(
        REVIEW_PLACE_ENUM,
        nullable=False,
    )

    method_association_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "school_method_associations.id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    reviewed_by_user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    protocol_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    protocol_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    protocol_original_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    protocol_stored_file_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    protocol_file_path: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    protocol_mime_type: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    protocol_file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    school_plan: Mapped[SchoolPlan] = relationship(
        "SchoolPlan",
        foreign_keys=[school_plan_id],
        lazy="raise",
    )

    reviewed_by_user: Mapped[User] = relationship(
        "User",
        foreign_keys=[reviewed_by_user_id],
        lazy="raise",
    )

    method_association: Mapped[
        SchoolMethodAssociation | None
    ] = relationship(
        "SchoolMethodAssociation",
        back_populates="task_reviews",
        foreign_keys=[method_association_id],
        lazy="raise",
    )

    review_results: Mapped[
        list["SchoolMonthPlanItemReviewResult"]
    ] = relationship(
        "SchoolMonthPlanItemReviewResult",
        back_populates="task_review",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )


class SchoolMonthPlanItemReviewResult(Base):
    """
    Результат рассмотрения одной задачи месячного плана
    в рамках конкретного заседания и протокола.
    """

    __tablename__ = "school_month_plan_item_review_results"

    __table_args__ = (
        UniqueConstraint(
            "month_item_id",
            "task_review_id",
            name="uq_review_result_month_item_task_review",
        ),
        Index(
            "ix_review_result_month_item_status",
            "month_item_id",
            "status",
        ),
        Index(
            "ix_review_result_task_review",
            "task_review_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    month_item_id: Mapped[int] = mapped_column(
        ForeignKey(
            "school_month_plan_items.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    task_review_id: Mapped[int] = mapped_column(
        ForeignKey(
            "school_task_reviews.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    review_place: Mapped[ReviewPlace] = mapped_column(
        REVIEW_PLACE_ENUM,
        nullable=False,
        index=True,
    )

    status: Mapped[PlanItemStatus] = mapped_column(
        PLAN_ITEM_STATUS_ENUM,
        nullable=False,
        default=PlanItemStatus.DONE,
        index=True,
    )

    protocol_document_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "task_execution_documents.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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

    month_item: Mapped[SchoolMonthPlanItem] = relationship(
        "SchoolMonthPlanItem",
        back_populates="review_results",
        lazy="raise",
    )

    task_review: Mapped[SchoolTaskReview] = relationship(
        "SchoolTaskReview",
        back_populates="review_results",
        foreign_keys=[task_review_id],
        lazy="raise",
    )

    protocol_document: Mapped[
        TaskExecutionDocument | None
    ] = relationship(
        "TaskExecutionDocument",
        foreign_keys=[protocol_document_id],
        lazy="raise",
    )

    reviewed_by_user: Mapped[User | None] = relationship(
        "User",
        foreign_keys=[reviewed_by_user_id],
        lazy="raise",
    )
