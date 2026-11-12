"""add question bank item reviews

Revision ID: 7c3df1aea578
Revises: 528a9f9a9379
Create Date: 2026-09-22 17:40:08.487267

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7c3df1aea578'
down_revision: Union[str, None] = '528a9f9a9379'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -----------------------------------------------------
    # PostgreSQL ENUM
    # -----------------------------------------------------

    question_bank_review_decision = postgresql.ENUM(
        "approved",
        "rejected",
        name="question_bank_review_decision",
        create_type=False,
    )

    question_bank_review_decision.create(
        op.get_bind(),
        checkfirst=True,
    )

    # -----------------------------------------------------
    # QUESTION BANK ITEM REVIEWS
    # -----------------------------------------------------

    op.create_table(
        "question_bank_item_reviews",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "question_bank_item_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "reviewer_user_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "decision",
            question_bank_review_decision,
            nullable=False,
        ),

        sa.Column(
            "comment",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["question_bank_item_id"],
            ["question_bank_items.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["reviewer_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),
    )

    # -----------------------------------------------------
    # INDEXES
    # -----------------------------------------------------

    op.create_index(
        "ix_question_bank_item_reviews_item",
        "question_bank_item_reviews",
        ["question_bank_item_id"],
        unique=False,
    )

    op.create_index(
        "ix_question_bank_item_reviews_reviewer",
        "question_bank_item_reviews",
        ["reviewer_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_question_bank_item_reviews_created",
        "question_bank_item_reviews",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    # -----------------------------------------------------
    # INDEXES / TABLE
    # -----------------------------------------------------

    op.drop_index(
        "ix_question_bank_item_reviews_created",
        table_name="question_bank_item_reviews",
    )

    op.drop_index(
        "ix_question_bank_item_reviews_reviewer",
        table_name="question_bank_item_reviews",
    )

    op.drop_index(
        "ix_question_bank_item_reviews_item",
        table_name="question_bank_item_reviews",
    )

    op.drop_table(
        "question_bank_item_reviews",
    )

    # -----------------------------------------------------
    # PostgreSQL ENUM
    # -----------------------------------------------------

    question_bank_review_decision = postgresql.ENUM(
        "approved",
        "rejected",
        name="question_bank_review_decision",
        create_type=False,
    )

    question_bank_review_decision.drop(
        op.get_bind(),
        checkfirst=True,
    )
