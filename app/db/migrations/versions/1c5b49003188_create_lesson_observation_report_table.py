"""create lesson observation report table

Revision ID: 1c5b49003188
Revises: f9f94b0af11f
Create Date: 2026-04-27 08:31:50.508378

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c5b49003188'
down_revision: Union[str, None] = 'f9f94b0af11f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

"""create lesson observation report table

Revision ID: xxxx_create_lesson_observation
Revises: <ТВОЯ_ПОСЛЕДНЯЯ_РЕВИЗИЯ>
Create Date: 2026-04-27

"""


def upgrade() -> None:
    op.create_table(
        "lesson_observation_reports",

        sa.Column("id", sa.Integer(), primary_key=True),

        # =========================
        # связи
        # =========================
        sa.Column(
            "month_item_id",
            sa.Integer(),
            sa.ForeignKey("school_month_plan_items.id", ondelete="CASCADE"),
            nullable=False,
        ),

        sa.Column(
            "task_execution_document_id",
            sa.Integer(),
            sa.ForeignKey("task_execution_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),

        sa.Column(
            "staff_member_id",
            sa.Integer(),
            sa.ForeignKey("school_staff_members.id", ondelete="SET NULL"),
            nullable=True,
        ),

        sa.Column(
            "observer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # =========================
        # snapshot учителя
        # =========================
        sa.Column("teacher_full_name", sa.String(length=255), nullable=True),
        sa.Column("teacher_position", sa.String(length=255), nullable=True),
        sa.Column("teacher_category", sa.String(length=255), nullable=True),
        sa.Column("teacher_subject", sa.String(length=255), nullable=True),

        # =========================
        # snapshot наблюдателя
        # =========================
        sa.Column("observer_full_name", sa.String(length=255), nullable=True),
        sa.Column("observer_position", sa.String(length=255), nullable=True),

        # =========================
        # данные урока
        # =========================
        sa.Column("school_name", sa.String(length=255), nullable=True),
        sa.Column("class_name", sa.String(length=100), nullable=True),
        sa.Column("group_name", sa.String(length=255), nullable=True),

        sa.Column("lesson_datetime", sa.DateTime(timezone=True), nullable=True),

        sa.Column("theme", sa.Text(), nullable=True),
        sa.Column("learning_objectives", sa.Text(), nullable=True),

        sa.Column("lesson_objectives_1", sa.Text(), nullable=True),
        sa.Column("lesson_objectives_2", sa.Text(), nullable=True),
        sa.Column("lesson_objectives_3", sa.Text(), nullable=True),

        sa.Column("lesson_plan_filename", sa.String(length=255), nullable=True),

        # =========================
        # оценивание
        # =========================
        sa.Column("col_sum_0", sa.Integer(), nullable=True),
        sa.Column("col_sum_1", sa.Integer(), nullable=True),
        sa.Column("col_sum_2", sa.Integer(), nullable=True),
        sa.Column("col_sum_3", sa.Integer(), nullable=True),

        sa.Column("total", sa.Integer(), nullable=True),

        # =========================
        # итоги
        # =========================
        sa.Column("suggestion_control", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),

        # =========================
        # файлы
        # =========================
        sa.Column("pdf_file", sa.String(length=255), nullable=True),
        sa.Column("pdf_signed_file", sa.String(length=255), nullable=True),
        sa.Column("qr_file", sa.String(length=255), nullable=True),

        # =========================
        # даты
        # =========================
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # =========================
    # constraints
    # =========================

    op.create_unique_constraint(
        "uq_lesson_observation_task_document",
        "lesson_observation_reports",
        ["task_execution_document_id"],
    )

    # =========================
    # индексы
    # =========================

    op.create_index(
        "ix_lesson_observation_month_item",
        "lesson_observation_reports",
        ["month_item_id"],
    )

    op.create_index(
        "ix_lesson_observation_document",
        "lesson_observation_reports",
        ["task_execution_document_id"],
    )

    op.create_index(
        "ix_lesson_observation_teacher",
        "lesson_observation_reports",
        ["staff_member_id"],
    )

    op.create_index(
        "ix_lesson_observation_observer",
        "lesson_observation_reports",
        ["observer_user_id"],
    )

    op.create_index(
        "ix_lesson_observation_lesson_datetime",
        "lesson_observation_reports",
        ["lesson_datetime"],
    )


def downgrade() -> None:
    op.drop_index("ix_lesson_observation_lesson_datetime", table_name="lesson_observation_reports")
    op.drop_index("ix_lesson_observation_observer", table_name="lesson_observation_reports")
    op.drop_index("ix_lesson_observation_teacher", table_name="lesson_observation_reports")
    op.drop_index("ix_lesson_observation_document", table_name="lesson_observation_reports")
    op.drop_index("ix_lesson_observation_month_item", table_name="lesson_observation_reports")

    op.drop_constraint(
        "uq_lesson_observation_task_document",
        "lesson_observation_reports",
        type_="unique",
    )

    op.drop_table("lesson_observation_reports")
