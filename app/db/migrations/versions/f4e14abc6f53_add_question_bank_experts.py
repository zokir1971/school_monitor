"""add question bank experts

Revision ID: f4e14abc6f53
Revises: 5869f896b73b
Create Date: 2026-10-02 10:20:33.591975

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f4e14abc6f53'
down_revision: Union[str, None] = '5869f896b73b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_bank_experts",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        # -------------------------------------------------
        # School / Subject
        # -------------------------------------------------

        sa.Column(
            "school_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "subject_id",
            sa.Integer(),
            nullable=False,
        ),

        # -------------------------------------------------
        # Personal data
        # -------------------------------------------------

        sa.Column(
            "iin",
            sa.String(length=12),
            nullable=False,
        ),

        sa.Column(
            "full_name",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "phone",
            sa.String(length=32),
            nullable=True,
        ),

        sa.Column(
            "email",
            sa.String(length=255),
            nullable=True,
        ),

        # -------------------------------------------------
        # Professional data
        # -------------------------------------------------

        sa.Column(
            "position_text",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "education_text",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "specialty_text",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "qualification_category_text",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "ped_experience_years",
            sa.Integer(),
            nullable=True,
        ),

        # -------------------------------------------------
        # Account
        # -------------------------------------------------

        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=True,
        ),

        # -------------------------------------------------
        # Status
        # -------------------------------------------------

        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),

        # -------------------------------------------------
        # Audit
        # -------------------------------------------------

        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            nullable=False,
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

        sa.Column(
            "deactivated_by_user_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "deactivated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # -------------------------------------------------
        # Primary key
        # -------------------------------------------------

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_question_bank_experts",
        ),

        # -------------------------------------------------
        # Foreign keys
        # -------------------------------------------------

        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            name="fk_qb_expert_school",
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_qb_expert_subject",
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_qb_expert_user",
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_qb_expert_created_by_user",
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["deactivated_by_user_id"],
            ["users.id"],
            name="fk_qb_expert_deactivated_by_user",
            ondelete="RESTRICT",
        ),

        # -------------------------------------------------
        # Business constraints
        # -------------------------------------------------

        sa.UniqueConstraint(
            "iin",
            "subject_id",
            name="uq_qb_expert_iin_subject",
        ),

        sa.CheckConstraint(
            "iin ~ '^[0-9]{12}$'",
            name="ck_qb_expert_iin_12_digits",
        ),

        sa.CheckConstraint(
            "ped_experience_years IS NULL "
            "OR ped_experience_years >= 0",
            name="ck_qb_expert_ped_experience_non_negative",
        ),
    )

    # -----------------------------------------------------
    # Indexes
    # -----------------------------------------------------

    op.create_index(
        "ix_qb_expert_school_active",
        "question_bank_experts",
        ["school_id", "is_active"],
        unique=False,
    )

    op.create_index(
        "ix_qb_expert_subject_active",
        "question_bank_experts",
        ["subject_id", "is_active"],
        unique=False,
    )

    op.create_index(
        "ix_qb_expert_user_active",
        "question_bank_experts",
        ["user_id", "is_active"],
        unique=False,
    )

    op.create_index(
        "ix_qb_expert_iin_active",
        "question_bank_experts",
        ["iin", "is_active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_qb_expert_iin_active",
        table_name="question_bank_experts",
    )

    op.drop_index(
        "ix_qb_expert_user_active",
        table_name="question_bank_experts",
    )

    op.drop_index(
        "ix_qb_expert_subject_active",
        table_name="question_bank_experts",
    )

    op.drop_index(
        "ix_qb_expert_school_active",
        table_name="question_bank_experts",
    )

    op.drop_table("question_bank_experts")
