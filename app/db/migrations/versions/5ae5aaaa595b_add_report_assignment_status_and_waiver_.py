"""add report assignment status and waiver fields

Revision ID: 5ae5aaaa595b
Revises: 103d127b583f
Create Date: 2026-08-10 09:23:28.973862

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5ae5aaaa595b'
down_revision: Union[str, None] = '103d127b583f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. PostgreSQL ENUM
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM pg_type
            WHERE typname = 'report_assignment_status_enum'
        ) THEN
            CREATE TYPE report_assignment_status_enum
            AS ENUM (
                'pending',
                'completed',
                'waived'
            );
        END IF;
    END
    $$;
    """)

    # 2. Добавляем status пока nullable=True
    op.add_column(
        "task_selected_report_assignments",
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "completed",
                "waived",
                name="report_assignment_status_enum",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    # 3. Поля WAIVED
    op.add_column(
        "task_selected_report_assignments",
        sa.Column(
            "waived_reason",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "task_selected_report_assignments",
        sa.Column(
            "waived_by_user_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "task_selected_report_assignments",
        sa.Column(
            "waived_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 4. Старые назначения считаем ожидающими выполнения
    op.execute("""
        UPDATE task_selected_report_assignments
        SET status = 'pending'
        WHERE status IS NULL;
    """)

    # 5. Теперь можно сделать status NOT NULL
    op.alter_column(
        "task_selected_report_assignments",
        "status",
        existing_type=sa.Enum(
            "pending",
            "completed",
            "waived",
            name="report_assignment_status_enum",
            create_type=False,
        ),
        nullable=False,
        server_default=sa.text("'pending'"),
    )

    # 6. FK на пользователя, который разрешил пропуск
    op.create_foreign_key(
        "fk_task_selected_report_assignments_waived_by_user_id",
        "task_selected_report_assignments",
        "users",
        ["waived_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # 7. Индекс статуса
    op.create_index(
        "ix_task_selected_report_assignments_status",
        "task_selected_report_assignments",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_selected_report_assignments_status",
        table_name="task_selected_report_assignments",
    )

    op.drop_constraint(
        "fk_task_selected_report_assignments_waived_by_user_id",
        "task_selected_report_assignments",
        type_="foreignkey",
    )

    op.drop_column(
        "task_selected_report_assignments",
        "waived_at",
    )

    op.drop_column(
        "task_selected_report_assignments",
        "waived_by_user_id",
    )

    op.drop_column(
        "task_selected_report_assignments",
        "waived_reason",
    )

    op.drop_column(
        "task_selected_report_assignments",
        "status",
    )

    op.execute("""
    DROP TYPE IF EXISTS report_assignment_status_enum;
    """)
