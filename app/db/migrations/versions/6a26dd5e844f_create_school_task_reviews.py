"""create school task reviews

Revision ID: 6a26dd5e844f
Revises: 0e56b0382948
Create Date: 2026-07-21 20:15:25.875728

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6a26dd5e844f'
down_revision: Union[str, None] = '0e56b0382948'
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


def upgrade() -> None:
    op.create_table(
        "school_task_reviews",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "school_plan_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "review_place",
            review_place_enum,
            nullable=False,
        ),

        sa.Column(
            "review_date",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),

        sa.Column(
            "reviewed_by_user_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "protocol_number",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "protocol_date",
            sa.Date(),
            nullable=True,
        ),

        sa.Column(
            "protocol_original_file_name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "protocol_stored_file_name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "protocol_file_path",
            sa.String(length=500),
            nullable=False,
        ),

        sa.Column(
            "protocol_mime_type",
            sa.String(length=150),
            nullable=False,
        ),

        sa.Column(
            "protocol_file_size",
            sa.BigInteger(),
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

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["school_plan_id"],
            ["school_plans.id"],
            name="fk_school_task_reviews_school_plan_id",
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            name="fk_school_task_reviews_reviewed_by_user_id",
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_school_task_reviews",
        ),
    )

    op.create_index(
        "ix_school_task_reviews_school_plan_id",
        "school_task_reviews",
        ["school_plan_id"],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_review_place",
        "school_task_reviews",
        ["review_place"],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_review_date",
        "school_task_reviews",
        ["review_date"],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_reviewed_by_user_id",
        "school_task_reviews",
        ["reviewed_by_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_plan_place_date",
        "school_task_reviews",
        [
            "school_plan_id",
            "review_place",
            "review_date",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_school_task_reviews_plan_place_date",
        table_name="school_task_reviews",
    )

    op.drop_index(
        "ix_school_task_reviews_reviewed_by_user_id",
        table_name="school_task_reviews",
    )

    op.drop_index(
        "ix_school_task_reviews_review_date",
        table_name="school_task_reviews",
    )

    op.drop_index(
        "ix_school_task_reviews_review_place",
        table_name="school_task_reviews",
    )

    op.drop_index(
        "ix_school_task_reviews_school_plan_id",
        table_name="school_task_reviews",
    )

    op.drop_table("school_task_reviews")
