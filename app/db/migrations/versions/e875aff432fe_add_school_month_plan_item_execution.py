"""add school_month_plan_item_execution

Revision ID: e875aff432fe
Revises: 95a07b9f83f8
Create Date: 2026-04-06 19:53:54.018161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e875aff432fe'
down_revision: Union[str, None] = '95a07b9f83f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "school_month_plan_item_executions",

        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column(
            "month_item_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column("control_scope", sa.String(length=50), nullable=True),
        sa.Column("control_form", sa.String(length=50), nullable=True),
        sa.Column("control_kind", sa.String(length=50), nullable=True),
        sa.Column("report_type", sa.String(length=50), nullable=True),

        sa.Column("evidence_note", sa.Text(), nullable=True),

        sa.Column("reference_text", sa.Text(), nullable=True),
        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),

        sa.Column("review_result", sa.Text(), nullable=True),
        sa.Column("planned_review_place", sa.String(length=255), nullable=True),

        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # 🔗 FK
        sa.ForeignKeyConstraint(
            ["month_item_id"],
            ["school_month_plan_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        # 🔥 1:1
        sa.UniqueConstraint(
            "month_item_id",
            name="uq_month_item_execution_one",
        ),
    )

    # 🔹 индексы
    op.create_index(
        "ix_execution_month_item",
        "school_month_plan_item_executions",
        ["month_item_id"],
    )

    op.create_index(
        "ix_execution_control_form",
        "school_month_plan_item_executions",
        ["control_form"],
    )


def downgrade():
    op.drop_index("ix_execution_control_form", table_name="school_month_plan_item_executions")
    op.drop_index("ix_execution_month_item", table_name="school_month_plan_item_executions")
    op.drop_table("school_month_plan_item_executions")
