"""add task_execution_documents

Revision ID: 13f7d43ab3a7
Revises: f626b7207088
Create Date: 2026-04-09 11:00:04.016129
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '13f7d43ab3a7'
down_revision: Union[str, None] = 'f626b7207088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

document_type_enum = postgresql.ENUM(
    "plan",
    "protocol",
    "act",
    "report",
    "reference",
    "other",
    name="document_type_enum",
    create_type=False,
)

task_document_status_enum = postgresql.ENUM(
    "draft",
    "uploaded",
    "submitted",
    "approved",
    "rejected",
    name="task_document_status_enum",
    create_type=False,
)

task_document_source_enum = postgresql.ENUM(
    "upload",
    "generated",
    "template",
    name="task_document_source_enum",
    create_type=False,
)


def upgrade() -> None:

    op.create_table(
        "task_execution_documents",
        sa.Column("id", sa.Integer(), nullable=False),

        sa.Column("month_item_id", sa.Integer(), nullable=False),
        sa.Column("required_document_id", sa.Integer(), nullable=True),

        sa.Column("document_type", document_type_enum, nullable=False),

        sa.Column("status", task_document_status_enum, nullable=False),
        sa.Column("source", task_document_source_enum, nullable=False),

        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")),

        sa.Column("title", sa.String(length=255), nullable=True),

        sa.Column("original_file_name", sa.String(length=255), nullable=True),
        sa.Column("stored_file_name", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),

        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),

        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("submitted_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),

        sa.ForeignKeyConstraint(
            ["month_item_id"],
            ["school_month_plan_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["required_document_id"],
            ["school_plan_row_11_required_documents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "month_item_id",
            "document_type",
            "version",
            name="uq_task_exec_doc_type_version",
        ),
    )

    op.create_index(
        "ix_task_execution_documents_month_item_id",
        "task_execution_documents",
        ["month_item_id"],
    )
    op.create_index(
        "ix_task_execution_documents_required_document_id",
        "task_execution_documents",
        ["required_document_id"],
    )
    op.create_index(
        "ix_task_execution_documents_document_type",
        "task_execution_documents",
        ["document_type"],
    )
    op.create_index(
        "ix_task_execution_documents_status",
        "task_execution_documents",
        ["status"],
    )

    op.create_index(
        "ix_task_exec_docs_month_item_status",
        "task_execution_documents",
        ["month_item_id", "status"],
    )
    op.create_index(
        "ix_task_exec_docs_month_item_current",
        "task_execution_documents",
        ["month_item_id", "is_current"],
    )
    op.create_index(
        "ix_task_exec_docs_required_document",
        "task_execution_documents",
        ["required_document_id"],
    )
    op.create_index(
        "ix_task_exec_docs_uploaded_by",
        "task_execution_documents",
        ["uploaded_by_user_id"],
    )

    op.alter_column("task_execution_documents", "version", server_default=None)
    op.alter_column("task_execution_documents", "is_current", server_default=None)
    op.alter_column("task_execution_documents", "is_final", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_task_exec_docs_uploaded_by", table_name="task_execution_documents")
    op.drop_index("ix_task_exec_docs_required_document", table_name="task_execution_documents")
    op.drop_index("ix_task_exec_docs_month_item_current", table_name="task_execution_documents")
    op.drop_index("ix_task_exec_docs_month_item_status", table_name="task_execution_documents")

    op.drop_index("ix_task_execution_documents_status", table_name="task_execution_documents")
    op.drop_index("ix_task_execution_documents_document_type", table_name="task_execution_documents")
    op.drop_index("ix_task_execution_documents_required_document_id", table_name="task_execution_documents")
    op.drop_index("ix_task_execution_documents_month_item_id", table_name="task_execution_documents")

    op.drop_table("task_execution_documents")

    bind = op.get_bind()
    task_document_source_enum.drop(bind, checkfirst=True)
    task_document_status_enum.drop(bind, checkfirst=True)
