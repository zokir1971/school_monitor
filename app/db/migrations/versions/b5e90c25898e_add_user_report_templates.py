"""add user report templates

Revision ID: b5e90c25898e
Revises: a7518f111088
Create Date: 2026-04-27 21:16:44.591966

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5e90c25898e'
down_revision: Union[str, None] = 'a7518f111088'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_report_templates",
        sa.Column("id", sa.Integer(), primary_key=True),

        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("report_type_id", sa.Integer(), nullable=True),

        sa.Column("report_code", sa.String(length=100), nullable=False),
        sa.Column("report_label", sa.String(length=255), nullable=True),

        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        sa.Column("content_html", sa.Text(), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),

        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["report_type_id"],
            ["report_types.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "owner_user_id",
            "report_code",
            "title",
            name="uq_user_report_template_owner_code_title",
        ),
    )

    op.create_index(
        "ix_user_report_templates_owner",
        "user_report_templates",
        ["owner_user_id"],
    )

    op.create_index(
        "ix_user_report_templates_report_type",
        "user_report_templates",
        ["report_type_id"],
    )

    op.create_index(
        "ix_user_report_templates_report_code",
        "user_report_templates",
        ["report_code"],
    )

    op.create_index(
        "ix_user_report_templates_owner_code_active",
        "user_report_templates",
        ["owner_user_id", "report_code", "is_active"],
    )

    op.add_column(
        "task_execution_documents",
        sa.Column("custom_template_id", sa.Integer(), nullable=True),
    )

    op.add_column(
        "task_execution_documents",
        sa.Column("template_mode", sa.String(length=50), nullable=True),
    )

    op.add_column(
        "task_execution_documents",
        sa.Column("custom_content_html", sa.Text(), nullable=True),
    )

    op.add_column(
        "task_execution_documents",
        sa.Column("custom_content_text", sa.Text(), nullable=True),
    )

    op.create_foreign_key(
        "fk_task_exec_docs_custom_template_id",
        "task_execution_documents",
        "user_report_templates",
        ["custom_template_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index(
        "ix_task_exec_docs_custom_template",
        "task_execution_documents",
        ["custom_template_id"],
    )

    op.create_index(
        "ix_task_exec_docs_template_mode",
        "task_execution_documents",
        ["template_mode"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_exec_docs_template_mode",
        table_name="task_execution_documents",
    )

    op.drop_index(
        "ix_task_exec_docs_custom_template",
        table_name="task_execution_documents",
    )

    op.drop_constraint(
        "fk_task_exec_docs_custom_template_id",
        "task_execution_documents",
        type_="foreignkey",
    )

    op.drop_column("task_execution_documents", "custom_content_text")
    op.drop_column("task_execution_documents", "custom_content_html")
    op.drop_column("task_execution_documents", "template_mode")
    op.drop_column("task_execution_documents", "custom_template_id")

    op.drop_index(
        "ix_user_report_templates_owner_code_active",
        table_name="user_report_templates",
    )

    op.drop_index(
        "ix_user_report_templates_report_code",
        table_name="user_report_templates",
    )

    op.drop_index(
        "ix_user_report_templates_report_type",
        table_name="user_report_templates",
    )

    op.drop_index(
        "ix_user_report_templates_owner",
        table_name="user_report_templates",
    )

    op.drop_table("user_report_templates")
