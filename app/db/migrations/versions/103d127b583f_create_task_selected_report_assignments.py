"""create task selected report assignments

Revision ID: 103d127b583f
Revises: e6be5a2b0308
Create Date: 2026-08-06 12:41:03.021542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '103d127b583f'
down_revision: Union[str, None] = 'e6be5a2b0308'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "task_selected_report_assignments"

UQ_SELECTED_REPORT = (
    "uq_task_selected_report_assignments_selected_report_id"
)

IX_STAFF_MEMBER = (
    "ix_task_selected_report_assignments_staff_member_id"
)

IX_ASSIGNED_BY_USER = (
    "ix_task_selected_report_assignments_assigned_by_user_id"
)


def upgrade() -> None:
    """
    Создать таблицу распределения выбранных отчётов.

    Один выбранный отчёт может быть назначен только
    одному сотруднику.

    Связи:

    - selected_report_id:
      конкретный отчёт, выбранный в алгоритме выполнения;

    - staff_member_id:
      сотрудник, который должен заполнить отчёт;

    - assigned_by_user_id:
      пользователь, выполнивший распределение отчётов.
    """

    op.create_table(
        TABLE_NAME,

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "selected_report_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "staff_member_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "assigned_by_user_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "assigned_at",
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
            ["selected_report_id"],
            ["task_execution_selected_reports.id"],
            name=(
                "fk_task_selected_report_assignments_"
                "selected_report_id"
            ),
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["staff_member_id"],
            ["school_staff_members.id"],
            name=(
                "fk_task_selected_report_assignments_"
                "staff_member_id"
            ),
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            name=(
                "fk_task_selected_report_assignments_"
                "assigned_by_user_id"
            ),
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_task_selected_report_assignments",
        ),

        sa.UniqueConstraint(
            "selected_report_id",
            name=UQ_SELECTED_REPORT,
        ),
    )

    op.create_index(
        IX_STAFF_MEMBER,
        TABLE_NAME,
        ["staff_member_id"],
        unique=False,
    )

    op.create_index(
        IX_ASSIGNED_BY_USER,
        TABLE_NAME,
        ["assigned_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    """
    Удалить таблицу распределения выбранных отчётов.
    """

    op.drop_index(
        IX_ASSIGNED_BY_USER,
        table_name=TABLE_NAME,
    )

    op.drop_index(
        IX_STAFF_MEMBER,
        table_name=TABLE_NAME,
    )

    op.drop_table(TABLE_NAME)
