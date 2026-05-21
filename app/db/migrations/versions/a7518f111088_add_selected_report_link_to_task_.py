"""add selected report link to task execution documents

Revision ID: a7518f111088
Revises: 1c5b49003188
Create Date: 2026-04-27 09:12:15.089280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7518f111088'
down_revision: Union[str, None] = '1c5b49003188'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_execution_documents",
        sa.Column("selected_report_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_task_exec_docs_selected_report_id",
        "task_execution_documents",
        "task_execution_selected_reports",
        ["selected_report_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_task_execution_documents_selected_report_id",
        "task_execution_documents",
        ["selected_report_id"],
        unique=False,
    )

    op.create_index(
        "ix_task_exec_docs_selected_report_current",
        "task_execution_documents",
        ["selected_report_id", "is_current"],
        unique=False,
    )

    op.create_unique_constraint(
        "uq_task_exec_doc_selected_report_version",
        "task_execution_documents",
        ["selected_report_id", "version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_task_exec_doc_selected_report_version",
        "task_execution_documents",
        type_="unique",
    )

    op.drop_index(
        "ix_task_exec_docs_selected_report_current",
        table_name="task_execution_documents",
    )

    op.drop_index(
        "ix_task_execution_documents_selected_report_id",
        table_name="task_execution_documents",
    )

    op.drop_constraint(
        "fk_task_exec_docs_selected_report_id",
        "task_execution_documents",
        type_="foreignkey",
    )

    op.drop_column("task_execution_documents", "selected_report_id")
