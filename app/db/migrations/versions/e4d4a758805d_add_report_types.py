"""add report_types

Revision ID: e4d4a758805d
Revises: 13f7d43ab3a7
Create Date: 2026-04-09 12:19:42.202372

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4d4a758805d'
down_revision: Union[str, None] = '13f7d43ab3a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

"""add report_types and link to task_execution_documents

Revision ID: add_report_types
Revises: 13f7d43ab3a7
"""


def upgrade():
    # -----------------------------
    # 1. Таблица report_types
    # -----------------------------
    op.create_table(
        "report_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name_kz", sa.String(length=255), nullable=False),
        sa.Column("name_ru", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="100"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_index(
        "ix_report_types_code",
        "report_types",
        ["code"],
    )

    # -----------------------------
    # 2. Добавляем поле в documents
    # -----------------------------
    op.add_column(
        "task_execution_documents",
        sa.Column("report_type_id", sa.Integer(), nullable=True),
    )

    op.create_index(
        "ix_task_execution_documents_report_type_id",
        "task_execution_documents",
        ["report_type_id"],
    )

    op.create_foreign_key(
        "fk_task_exec_doc_report_type",
        "task_execution_documents",
        "report_types",
        ["report_type_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -----------------------------
    # 3. Начальные данные
    # -----------------------------
    op.execute("""
        INSERT INTO report_types (code, name_kz, sort_order) VALUES
        ('lesson_observation', 'Сабақты бақылау парағы', 1),
        ('knowledge_quality_table', 'Білім сапасының кестесі', 2),
        ('document_analysis', 'Құжаттарды талдау', 3),
        ('analytical_reference', 'Анықтама', 4),
        ('class_summary', 'Жалпылама талдау кестесі', 5),
        ('teacher_analysis', 'Мұғалім жұмысының талдауы', 6)
    """)


def downgrade():
    op.drop_constraint(
        "fk_task_exec_doc_report_type",
        "task_execution_documents",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_task_execution_documents_report_type_id",
        table_name="task_execution_documents",
    )

    op.drop_column("task_execution_documents", "report_type_id")

    op.drop_index("ix_report_types_code", table_name="report_types")
    op.drop_table("report_types")
