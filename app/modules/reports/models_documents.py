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
from sqlalchemy.dialects.postgresql import JSONB
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
    from app.modules.reports.models_report_signature_token import ReportSignatureToken


class TaskExecutionDocument(Base):
    __tablename__ = "task_execution_documents"
    __table_args__ = (
        UniqueConstraint(
            "month_item_id",
            "required_document_id",
            "report_code",
            "version",
            name="uq_task_exec_doc_required_report_version",
        ),
        UniqueConstraint(
            "selected_report_id",
            "version",
            name="uq_task_exec_doc_selected_report_version",
        ),
        Index(
            "ix_task_exec_docs_selected_report_current",
            "selected_report_id",
            "is_current",
        ),
        Index("ix_task_exec_docs_month_item_status", "month_item_id", "status"),
        Index("ix_task_exec_docs_month_item_current", "month_item_id", "is_current"),
        Index("ix_task_exec_docs_required_document", "required_document_id"),
        Index("ix_task_exec_docs_uploaded_by", "uploaded_by_user_id"),
        Index(
            "ix_task_exec_docs_month_required_current",
            "month_item_id",
            "required_document_id",
            "is_current",
        ),
        Index(
            "ix_task_exec_docs_month_report_current",
            "month_item_id",
            "report_code",
            "is_current",
        ),
        Index("ix_task_exec_docs_template_mode", "template_mode"),
        Index("ix_task_exec_docs_custom_template", "custom_template_id"),
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

    report_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    selected_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_execution_selected_reports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    report_code: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    report_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
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

    custom_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_report_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    template_mode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    custom_content_html: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    custom_content_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    # копия с UserReportTemplate применяется к конкретной задаче
    schema_json: Mapped[dict | None] = mapped_column(
        JSONB,
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

    report_type: Mapped["ReportTypeModel | None"] = relationship(
        "ReportTypeModel",
        lazy="selectin",
    )

    selected_report: Mapped["TaskExecutionSelectedReport | None"] = relationship(
        "TaskExecutionSelectedReport",
        lazy="selectin",
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

    custom_template: Mapped["UserReportTemplate | None"] = relationship(
        "UserReportTemplate",
        lazy="selectin",
    )

    signature_tokens: Mapped[list["ReportSignatureToken"]] = relationship(
        "ReportSignatureToken",
        back_populates="document",
        cascade="all, delete-orphan",
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

    selected_report_links: Mapped[list["TaskExecutionSelectedReport"]] = relationship(
        "TaskExecutionSelectedReport",
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

    review_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    completion_mode: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

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

    selected_reports: Mapped[list["TaskExecutionSelectedReport"]] = relationship(
        "TaskExecutionSelectedReport",
        back_populates="execution_data",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class TaskExecutionSelectedReport(Base):
    __tablename__ = "task_execution_selected_reports"
    __table_args__ = (
        UniqueConstraint(
            "execution_data_id",
            "report_type_id",
            "target_kind",
            "target_value",
            name="uq_task_exec_selected_report_unique",
        ),
        Index(
            "ix_task_exec_selected_reports_execution_data",
            "execution_data_id",
        ),
        Index(
            "ix_task_exec_selected_reports_report_type",
            "report_type_id",
        ),
        Index(
            "ix_task_exec_selected_reports_target",
            "target_kind",
            "target_value",
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

    target_kind: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    target_value: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    target_label: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    execution_data: Mapped["TaskExecutionData"] = relationship(
        "TaskExecutionData",
        back_populates="selected_reports",
    )

    report_type: Mapped["ReportTypeModel"] = relationship(
        "ReportTypeModel",
        back_populates="selected_report_links",
        lazy="selectin",
    )
