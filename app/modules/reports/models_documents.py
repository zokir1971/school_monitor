from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
from app.db.types import (
    DOCUMENT_TYPE_ENUM,
    TASK_DOCUMENT_SOURCE_ENUM,
    TASK_DOCUMENT_STATUS_ENUM,
)
from app.modules.reports.enums import (
    DocumentType,
    TaskDocumentSource,
    TaskDocumentStatus,
)

if TYPE_CHECKING:
    from app.modules.planning.models_month_plan import SchoolMonthPlanItem
    from app.modules.planning.models_school import SchoolPlanRow11RequiredDocument  # noqa: F401
    from app.modules.users.models import User  # noqa: F401


class TaskExecutionDocument(Base):
    __tablename__ = "task_execution_documents"
    __table_args__ = (
        UniqueConstraint(
            "month_item_id",
            "document_type",
            "version",
            name="uq_task_exec_doc_type_version",
        ),
        Index("ix_task_exec_docs_month_item_status", "month_item_id", "status"),
        Index("ix_task_exec_docs_month_item_current", "month_item_id", "is_current"),
        Index("ix_task_exec_docs_required_document", "required_document_id"),
        Index("ix_task_exec_docs_uploaded_by", "uploaded_by_user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    month_item_id: Mapped[int] = mapped_column(
        ForeignKey("school_month_plan_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    required_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("school_plan_row_11_required_documents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    document_type: Mapped[DocumentType] = mapped_column(
        DOCUMENT_TYPE_ENUM,
        nullable=False,
        index=True,
    )

    status: Mapped[TaskDocumentStatus] = mapped_column(
        TASK_DOCUMENT_STATUS_ENUM,
        nullable=False,
        default=TaskDocumentStatus.DRAFT,
        index=True,
    )

    source: Mapped[TaskDocumentSource] = mapped_column(
        TASK_DOCUMENT_SOURCE_ENUM,
        nullable=False,
        default=TaskDocumentSource.UPLOAD,
    )

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )

    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    original_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stored_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    submitted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
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

    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    month_item: Mapped["SchoolMonthPlanItem"] = relationship(
        "SchoolMonthPlanItem",
        back_populates="execution_documents",
    )

    required_document: Mapped["SchoolPlanRow11RequiredDocument | None"] = relationship(
        "SchoolPlanRow11RequiredDocument",
        back_populates="task_execution_documents",
    )

    uploaded_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[uploaded_by_user_id],
        lazy="selectin",
    )

    submitted_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[submitted_by_user_id],
        lazy="selectin",
    )

    reviewed_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[reviewed_by_user_id],
        lazy="selectin",
    )


class ReportTypeModel(Base):
    __tablename__ = "report_types"

    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    name_kz: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[str | None] = mapped_column(String(255), nullable=True)

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
    )

    task_execution_data_links: Mapped[list["TaskExecutionDataReportType"]] = relationship(
        "TaskExecutionDataReportType",
        back_populates="report_type",
        lazy="selectin",
    )


class TaskExecutionData(Base):
    __tablename__ = "task_execution_data"
    __table_args__ = (
        Index("ix_task_execution_data_month_item", "month_item_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    month_item_id: Mapped[int] = mapped_column(
        ForeignKey("school_month_plan_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    control_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_form: Mapped[str | None] = mapped_column(Text, nullable=True)
    control_kind: Mapped[str | None] = mapped_column(Text, nullable=True)

    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_review_place: Mapped[str | None] = mapped_column(Text, nullable=True)

    reference_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)

    reference_file_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    month_item: Mapped["SchoolMonthPlanItem"] = relationship(
        "SchoolMonthPlanItem",
        back_populates="execution_data",
    )

    report_type_links: Mapped[list["TaskExecutionDataReportType"]] = relationship(
        "TaskExecutionDataReportType",
        back_populates="execution_data",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TaskExecutionDataReportType(Base):
    __tablename__ = "task_execution_data_report_types"
    __table_args__ = (
        UniqueConstraint(
            "execution_data_id",
            "report_type_id",
            name="uq_task_execution_data_report_type",
        ),
        Index(
            "ix_task_execution_data_report_types_execution_data_id",
            "execution_data_id",
        ),
        Index(
            "ix_task_execution_data_report_types_report_type_id",
            "report_type_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    execution_data_id: Mapped[int] = mapped_column(
        ForeignKey("task_execution_data.id", ondelete="CASCADE"),
        nullable=False,
    )

    report_type_id: Mapped[int] = mapped_column(
        ForeignKey("report_types.id", ondelete="CASCADE"),
        nullable=False,
    )

    execution_data: Mapped["TaskExecutionData"] = relationship(
        "TaskExecutionData",
        back_populates="report_type_links",
    )

    report_type: Mapped["ReportTypeModel"] = relationship(
        "ReportTypeModel",
        back_populates="task_execution_data_links",
        lazy="selectin",
    )
