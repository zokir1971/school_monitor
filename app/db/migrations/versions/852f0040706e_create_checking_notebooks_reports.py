"""create checking_notebooks_reports

Revision ID: 852f0040706e
Revises: 786e190f58ac
Create Date: 2026-05-04 18:44:25.918388

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '852f0040706e'
down_revision: Union[str, None] = '786e190f58ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "checking_notebooks_reports",

        # PK
        sa.Column("id", sa.Integer(), nullable=False),

        # =========================
        # Базовые связи
        # =========================
        sa.Column("month_item_id", sa.Integer(), nullable=False),
        sa.Column("task_execution_document_id", sa.Integer(), nullable=False),
        sa.Column("user_template_id", sa.Integer(), nullable=True),
        sa.Column("observer_user_id", sa.Integer(), nullable=True),

        sa.Column("selected_report_id", sa.Integer(), nullable=True),

        # =========================
        # Snapshot
        # =========================
        sa.Column("school_name", sa.String(length=255), nullable=True),

        sa.Column("checker_name", sa.String(length=255), nullable=True),
        sa.Column("checker_post", sa.String(length=255), nullable=True),

        sa.Column("teacher_name", sa.String(length=255), nullable=True),
        sa.Column("class_name", sa.String(length=100), nullable=True),
        sa.Column("subject_name", sa.String(length=255), nullable=True),

        sa.Column("check_date", sa.DateTime(timezone=True), nullable=True),

        # =========================
        # Таблица данных
        # =========================
        sa.Column("rows_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # =========================
        # Итоги
        # =========================
        sa.Column("total_score", sa.Integer(), nullable=True),
        sa.Column("max_score", sa.Integer(), nullable=True),
        sa.Column("percent", sa.Integer(), nullable=True),
        sa.Column("level", sa.String(length=100), nullable=True),

        sa.Column("conclusion", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),

        # =========================
        # Файлы
        # =========================
        sa.Column("pdf_file", sa.String(length=255), nullable=True),
        sa.Column("pdf_signed_file", sa.String(length=255), nullable=True),
        sa.Column("qr_file", sa.String(length=255), nullable=True),

        # =========================
        # Даты
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

        # PK
        sa.PrimaryKeyConstraint("id"),

        # FK
        sa.ForeignKeyConstraint(
            ["month_item_id"],
            ["school_month_plan_items.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_execution_document_id"],
            ["task_execution_documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_template_id"],
            ["user_report_templates.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["observer_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )

    # =========================
    # UNIQUE
    # =========================
    op.create_unique_constraint(
        "uq_checking_notebooks_task_document",
        "checking_notebooks_reports",
        ["task_execution_document_id"],
    )

    # =========================
    # INDEXES
    # =========================
    op.create_index(
        "ix_checking_notebooks_month_item",
        "checking_notebooks_reports",
        ["month_item_id"],
    )

    op.create_index(
        "ix_checking_notebooks_document",
        "checking_notebooks_reports",
        ["task_execution_document_id"],
    )

    op.create_index(
        "ix_checking_notebooks_template",
        "checking_notebooks_reports",
        ["user_template_id"],
    )

    op.create_index(
        "ix_checking_notebooks_observer",
        "checking_notebooks_reports",
        ["observer_user_id"],
    )

    op.create_index(
        "ix_checking_notebooks_check_date",
        "checking_notebooks_reports",
        ["check_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_checking_notebooks_check_date", table_name="checking_notebooks_reports")
    op.drop_index("ix_checking_notebooks_observer", table_name="checking_notebooks_reports")
    op.drop_index("ix_checking_notebooks_template", table_name="checking_notebooks_reports")
    op.drop_index("ix_checking_notebooks_document", table_name="checking_notebooks_reports")
    op.drop_index("ix_checking_notebooks_month_item", table_name="checking_notebooks_reports")

    op.drop_constraint(
        "uq_checking_notebooks_task_document",
        "checking_notebooks_reports",
        type_="unique",
    )

    op.drop_table("checking_notebooks_reports")
