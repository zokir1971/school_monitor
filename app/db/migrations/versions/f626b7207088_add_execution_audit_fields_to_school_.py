"""add execution audit fields to school_month_plan_items

Revision ID: f626b7207088
Revises: ca63f824fbfd
Create Date: 2026-04-07 23:13:33.964133

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f626b7207088'
down_revision: Union[str, None] = 'ca63f824fbfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "school_month_plan_items",
        sa.Column("executed_at", sa.Date(), nullable=True),
    )
    op.add_column(
        "school_month_plan_items",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "school_month_plan_items",
        sa.Column("completed_by_user_id", sa.Integer(), nullable=True),
    )

    op.create_foreign_key(
        "fk_month_plan_items_completed_by_user",
        "school_month_plan_items",
        "users",
        ["completed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_month_plan_items_executed_at",
        "school_month_plan_items",
        ["executed_at"],
    )

    op.create_index(
        "ix_month_plan_items_completed_at",
        "school_month_plan_items",
        ["completed_at"],
    )

    op.create_index(
        "ix_month_plan_items_completed_by",
        "school_month_plan_items",
        ["completed_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_month_plan_items_completed_by", table_name="school_month_plan_items")
    op.drop_index("ix_month_plan_items_completed_at", table_name="school_month_plan_items")
    op.drop_index("ix_month_plan_items_executed_at", table_name="school_month_plan_items")

    op.drop_constraint(
        "fk_month_plan_items_completed_by_user",
        "school_month_plan_items",
        type_="foreignkey",
    )

    op.drop_column("school_month_plan_items", "completed_by_user_id")
    op.drop_column("school_month_plan_items", "completed_at")
    op.drop_column("school_month_plan_items", "executed_at")
