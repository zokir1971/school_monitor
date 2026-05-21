"""refactor task execution models and add reviewed status

Revision ID: 2e55f7a3c351
Revises: 82e17f0ff91e
Create Date: 2026-04-21 13:26:00.928787

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2e55f7a3c351"
down_revision: Union[str, None] = "82e17f0ff91e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add new enum value for school_month_plan_items.status
    # IMPORTANT:
    # Replace 'plan_item_status' below if your real PostgreSQL enum type name is different.
    op.execute("ALTER TYPE plan_item_status ADD VALUE IF NOT EXISTS 'reviewed'")

    # 2) Create new table that stores which report type is selected
    #    for which object/subject/target.
    op.create_table(
        "task_execution_selected_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("execution_data_id", sa.Integer(), nullable=False),
        sa.Column("report_type_id", sa.Integer(), nullable=False),
        sa.Column("target_kind", sa.String(length=50), nullable=False),
        sa.Column("target_value", sa.String(length=255), nullable=False),
        sa.Column("target_label", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["execution_data_id"],
            ["task_execution_data.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["report_type_id"],
            ["report_types.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_data_id",
            "report_type_id",
            "target_kind",
            "target_value",
            name="uq_task_exec_selected_report_unique",
        ),
    )
    op.create_index(
        "ix_task_exec_selected_reports_execution_data",
        "task_execution_selected_reports",
        ["execution_data_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_exec_selected_reports_report_type",
        "task_execution_selected_reports",
        ["report_type_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_exec_selected_reports_target",
        "task_execution_selected_reports",
        ["target_kind", "target_value"],
        unique=False,
    )

    # 3) Drop old execution_data <-> report_type m2m table
    op.drop_index(
        "ix_task_execution_data_report_types_execution_data_id",
        table_name="task_execution_data_report_types",
    )
    op.drop_index(
        "ix_task_execution_data_report_types_report_type_id",
        table_name="task_execution_data_report_types",
    )
    op.drop_table("task_execution_data_report_types")

    # 4) Remove obsolete columns from task_execution_data
    op.drop_column("task_execution_data", "recommendations")
    op.drop_column("task_execution_data", "evidence_note")
    op.drop_column("task_execution_data", "reference_file_note")
    op.drop_column("task_execution_data", "reference_text")
    op.drop_column("task_execution_data", "conclusion")
    op.drop_column("task_execution_data", "planned_review_place")
    op.drop_column("task_execution_data", "notes")

    # 5) Remove obsolete columns from task_execution_documents
    # Keep only upload/final-review oriented document structure.
    op.drop_index(
        "ix_task_execution_documents_report_type_id",
        table_name="task_execution_documents",
    )
    op.drop_constraint(
        "fk_task_exec_doc_report_type",
        "task_execution_documents",
        type_="foreignkey",
    )
    op.drop_column("task_execution_documents", "report_type_id")
    op.drop_column("task_execution_documents", "notes")
    op.drop_column("task_execution_documents", "content_html")


def downgrade() -> None:
    # 1) Restore removed columns in task_execution_documents
    op.add_column(
        "task_execution_documents",
        sa.Column("content_html", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_documents",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_documents",
        sa.Column("report_type_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_exec_doc_report_type",
        "task_execution_documents",
        "report_types",
        ["report_type_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_task_execution_documents_report_type_id",
        "task_execution_documents",
        ["report_type_id"],
        unique=False,
    )

    # 2) Restore removed columns in task_execution_data
    op.add_column(
        "task_execution_data",
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_data",
        sa.Column("planned_review_place", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_data",
        sa.Column("conclusion", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_data",
        sa.Column("reference_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_data",
        sa.Column("reference_file_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_data",
        sa.Column("evidence_note", sa.Text(), nullable=True),
    )
    op.add_column(
        "task_execution_data",
        sa.Column("recommendations", sa.Text(), nullable=True),
    )

    # 3) Recreate old m2m table
    op.create_table(
        "task_execution_data_report_types",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("execution_data_id", sa.Integer(), nullable=False),
        sa.Column("report_type_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_data_id"],
            ["task_execution_data.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["report_type_id"],
            ["report_types.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "execution_data_id",
            "report_type_id",
            name="uq_task_execution_data_report_type",
        ),
    )
    op.create_index(
        "ix_task_execution_data_report_types_execution_data_id",
        "task_execution_data_report_types",
        ["execution_data_id"],
        unique=False,
    )
    op.create_index(
        "ix_task_execution_data_report_types_report_type_id",
        "task_execution_data_report_types",
        ["report_type_id"],
        unique=False,
    )

    # 4) Drop new selected reports table
    op.drop_index(
        "ix_task_exec_selected_reports_target",
        table_name="task_execution_selected_reports",
    )
    op.drop_index(
        "ix_task_exec_selected_reports_report_type",
        table_name="task_execution_selected_reports",
    )
    op.drop_index(
        "ix_task_exec_selected_reports_execution_data",
        table_name="task_execution_selected_reports",
    )
    op.drop_table("task_execution_selected_reports")

    # NOTE:
    # PostgreSQL enum value 'reviewed' is intentionally not removed in downgrade.
    # Removing enum values safely requires a more complex recreate-type workflow.
