"""add ai question generation runs

Revision ID: 528a9f9a9379
Revises: 479442dac1ef
Create Date: 2026-09-21 18:05:20.953245

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '528a9f9a9379'
down_revision: Union[str, None] = '479442dac1ef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================
    # 1. PostgreSQL ENUM
    # =========================================================

    generation_status_enum = postgresql.ENUM(
        "running",
        "completed",
        "failed",
        name="ai_question_generation_run_status",
        create_type=False,
    )

    generation_status_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # =========================================================
    # 2. TABLE
    # =========================================================

    op.create_table(
        "ai_question_generation_runs",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "blueprint_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "status",
            generation_status_enum,
            nullable=False,
        ),

        sa.Column(
            "question_count",
            sa.SmallInteger(),
            nullable=False,
        ),

        sa.Column(
            "error_code",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.CheckConstraint(
            "question_count > 0",
            name=(
                "ck_ai_question_generation_runs_"
                "question_count_positive"
            ),
        ),

        sa.ForeignKeyConstraint(
            ["blueprint_id"],
            ["assessment_blueprints.id"],
            name=(
                "fk_ai_question_generation_runs_"
                "blueprint_id"
            ),
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=(
                "fk_ai_question_generation_runs_"
                "created_by_user_id"
            ),
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_ai_question_generation_runs",
        ),
    )

    # =========================================================
    # 3. NORMAL INDEXES
    # =========================================================

    op.create_index(
        "ix_ai_question_generation_runs_blueprint",
        "ai_question_generation_runs",
        ["blueprint_id"],
        unique=False,
    )

    op.create_index(
        "ix_ai_question_generation_runs_status",
        "ai_question_generation_runs",
        ["status"],
        unique=False,
    )

    # =========================================================
    # 4. CONCURRENCY GUARD
    # =========================================================
    #
    # Для одного Blueprint разрешён максимум
    # один RUNNING generation.
    #
    # COMPLETED / FAILED записей может быть сколько угодно.
    # =========================================================

    op.create_index(
        "uq_ai_question_generation_runs_one_running",
        "ai_question_generation_runs",
        ["blueprint_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'running'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_ai_question_generation_runs_one_running",
        table_name="ai_question_generation_runs",
    )

    op.drop_index(
        "ix_ai_question_generation_runs_status",
        table_name="ai_question_generation_runs",
    )

    op.drop_index(
        "ix_ai_question_generation_runs_blueprint",
        table_name="ai_question_generation_runs",
    )

    op.drop_table(
        "ai_question_generation_runs"
    )

    generation_status_enum = postgresql.ENUM(
        "running",
        "completed",
        "failed",
        name="ai_question_generation_run_status",
        create_type=False,
    )

    generation_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )
