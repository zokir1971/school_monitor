"""add report type fields to task execution documents

Revision ID: 8e49b08e1fff
Revises: b389d8705969
Create Date: 2026-04-24 17:33:34.882658

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8e49b08e1fff'
down_revision: Union[str, None] = 'b389d8705969'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_execution_documents",
        sa.Column("report_type_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "task_execution_documents",
        sa.Column("report_code", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "task_execution_documents",
        sa.Column("report_label", sa.String(length=255), nullable=True),
    )

    op.create_foreign_key(
        "fk_task_exec_docs_report_type_id",
        "task_execution_documents",
        "report_types",
        ["report_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_task_execution_documents_report_type_id",
        "task_execution_documents",
        ["report_type_id"],
        unique=False,
    )

    op.create_index(
        "ix_task_execution_documents_report_code",
        "task_execution_documents",
        ["report_code"],
        unique=False,
    )

    op.create_index(
        "ix_task_exec_docs_month_required_current",
        "task_execution_documents",
        ["month_item_id", "required_document_id", "is_current"],
        unique=False,
    )

    op.create_index(
        "ix_task_exec_docs_month_report_current",
        "task_execution_documents",
        ["month_item_id", "report_code", "is_current"],
        unique=False,
    )

    op.drop_constraint(
        "uq_task_exec_doc_type_version",
        "task_execution_documents",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_task_exec_doc_required_report_version",
        "task_execution_documents",
        ["month_item_id", "required_document_id", "report_code", "version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_task_exec_doc_required_report_version",
        "task_execution_documents",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_task_exec_doc_type_version",
        "task_execution_documents",
        ["month_item_id", "document_type", "version"],
    )

    op.drop_index(
        "ix_task_exec_docs_month_report_current",
        table_name="task_execution_documents",
    )

    op.drop_index(
        "ix_task_exec_docs_month_required_current",
        table_name="task_execution_documents",
    )

    op.drop_index(
        "ix_task_execution_documents_report_code",
        table_name="task_execution_documents",
    )

    op.drop_index(
        "ix_task_execution_documents_report_type_id",
        table_name="task_execution_documents",
    )

    op.drop_constraint(
        "fk_task_exec_docs_report_type_id",
        "task_execution_documents",
        type_="foreignkey",
    )

    op.drop_column("task_execution_documents", "report_label")
    op.drop_column("task_execution_documents", "report_code")
    op.drop_column("task_execution_documents", "report_type_id")
