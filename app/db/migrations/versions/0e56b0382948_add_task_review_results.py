"""add task review results

Revision ID: 0e56b0382948
Revises: 7c6f95ef9eca
Create Date: 2026-07-09 10:27:00.499384

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0e56b0382948"
down_revision: Union[str, None] = "7c6f95ef9eca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


review_place_enum = postgresql.ENUM(
    "ped_council",
    "method_council",
    "director_council",
    "administrative_council",
    "method_assoc",
    name="review_place",
    create_type=False,
)

plan_item_status_enum = postgresql.ENUM(
    "todo",
    "in_progress",
    "done",
    "reviewed",
    "not_executed",
    name="plan_item_status",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "school_month_plan_item_review_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month_item_id", sa.Integer(), nullable=False),
        sa.Column("review_place", review_place_enum, nullable=False),
        sa.Column(
            "status",
            plan_item_status_enum,
            nullable=False,
            server_default=sa.text("'done'::plan_item_status"),
        ),
        sa.Column("protocol_document_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["month_item_id"],
            ["school_month_plan_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["protocol_document_id"],
            ["task_execution_documents.id"],
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
            "review_place",
            name="uq_month_item_review_result_place",
        ),
    )

    op.create_index(
        "ix_review_result_month_item_place_status",
        "school_month_plan_item_review_results",
        ["month_item_id", "review_place", "status"],
        unique=False,
    )
    op.create_index(
        "ix_review_result_month_item_id",
        "school_month_plan_item_review_results",
        ["month_item_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_result_review_place",
        "school_month_plan_item_review_results",
        ["review_place"],
        unique=False,
    )
    op.create_index(
        "ix_review_result_status",
        "school_month_plan_item_review_results",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_review_result_protocol_document_id",
        "school_month_plan_item_review_results",
        ["protocol_document_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_result_reviewed_by_user_id",
        "school_month_plan_item_review_results",
        ["reviewed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_result_reviewed_at",
        "school_month_plan_item_review_results",
        ["reviewed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_review_result_reviewed_at",
        table_name="school_month_plan_item_review_results",
    )
    op.drop_index(
        "ix_review_result_reviewed_by_user_id",
        table_name="school_month_plan_item_review_results",
    )
    op.drop_index(
        "ix_review_result_protocol_document_id",
        table_name="school_month_plan_item_review_results",
    )
    op.drop_index(
        "ix_review_result_status",
        table_name="school_month_plan_item_review_results",
    )
    op.drop_index(
        "ix_review_result_review_place",
        table_name="school_month_plan_item_review_results",
    )
    op.drop_index(
        "ix_review_result_month_item_id",
        table_name="school_month_plan_item_review_results",
    )
    op.drop_index(
        "ix_review_result_month_item_place_status",
        table_name="school_month_plan_item_review_results",
    )

    op.drop_table("school_month_plan_item_review_results")
