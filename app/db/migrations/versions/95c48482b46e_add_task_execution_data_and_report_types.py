"""add task execution data and report types

Revision ID: 95c48482b46e
Revises: a283836b14d3
Create Date: 2026-04-12 20:29:22.891158

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '95c48482b46e'
down_revision: Union[str, None] = 'a283836b14d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------
    # task_execution_data
    # ---------------------------------------------------------
    op.create_table(
        "task_execution_data",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month_item_id", sa.Integer(), nullable=False),
        sa.Column("control_scope", sa.Text(), nullable=True),
        sa.Column("control_form", sa.Text(), nullable=True),
        sa.Column("control_kind", sa.Text(), nullable=True),
        sa.Column("evidence_note", sa.Text(), nullable=True),
        sa.Column("planned_review_place", sa.Text(), nullable=True),
        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("reference_file_note", sa.Text(), nullable=True),
        sa.Column("review_result", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["month_item_id"],
            ["school_month_plan_items.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("month_item_id"),
    )
    op.create_index(
        "ix_task_execution_data_month_item",
        "task_execution_data",
        ["month_item_id"],
        unique=False,
    )

    # ---------------------------------------------------------
    # task_execution_data_report_types
    # ---------------------------------------------------------
    op.create_table(
        "task_execution_data_report_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("execution_data_id", sa.Integer(), nullable=False),
        sa.Column("report_type_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_data_id"],
            ["task_execution_data.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["report_type_id"],
            ["report_types.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_data_id",
            "report_type_id",
            name="uq_task_execution_data_report_type",
        ),
    )
    op.create_index(
        "ix_task_execution_data_report_types_execution_data_id",
        "task_execution_data_report_types",
        ["execution_data_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_execution_data_report_types_report_type_id",
        "task_execution_data_report_types",
        ["report_type_id"],
        unique=False,
    )


def downgrade() -> None:
    # ---------------------------------------------------------
    # task_execution_data_report_types
    # ---------------------------------------------------------
    op.drop_index(
        "ix_task_execution_data_report_types_report_type_id",
        table_name="task_execution_data_report_types",
    )
    op.drop_index(
        "ix_task_execution_data_report_types_execution_data_id",
        table_name="task_execution_data_report_types",
    )
    op.drop_table("task_execution_data_report_types")

    # ---------------------------------------------------------
    # task_execution_data
    # ---------------------------------------------------------
    op.drop_index(
        "ix_task_execution_data_month_item",
        table_name="task_execution_data",
    )
    op.drop_table("task_execution_data")

    # ---------------------------------------------------------
    # report_types
    # ---------------------------------------------------------
    op.drop_index(op.f("ix_report_types_code"), table_name="report_types")
    op.drop_table("report_types")
