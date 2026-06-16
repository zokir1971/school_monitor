# app/modules/reports/models/report_signature_token.py

from sqlalchemy import (
    String,
    Text,
    DateTime,
    Boolean,
    Integer,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db.base import Base


class ReportSignatureToken(Base):
    __tablename__ = "report_signature_tokens"

    __table_args__ = (
        Index(
            "ix_report_signature_tokens_code_active",
            "code",
            "is_active",
        ),
        Index(
            "ix_report_signature_tokens_report",
            "report_type",
            "report_id",
        ),
        Index(
            "ix_report_signature_tokens_document",
            "document_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    code: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
    )

    token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    report_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    report_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    document_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "task_execution_documents.id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    # -------------------------
    # Relations
    # -------------------------

    document: Mapped["TaskExecutionDocument | None"] = relationship(
        "TaskExecutionDocument",
        back_populates="signature_tokens",
        lazy="selectin",
    )
