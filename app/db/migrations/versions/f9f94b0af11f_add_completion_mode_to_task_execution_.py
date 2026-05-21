"""add completion mode to task execution data

Revision ID: f9f94b0af11f
Revises: 8e49b08e1fff
Create Date: 2026-04-24 18:51:19.312340

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9f94b0af11f'
down_revision: Union[str, None] = '8e49b08e1fff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_execution_data",
        sa.Column("completion_mode", sa.String(length=50), nullable=True),
    )

    op.create_index(
        "ix_task_execution_data_completion_mode",
        "task_execution_data",
        ["completion_mode"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_task_execution_data_completion_mode",
        table_name="task_execution_data",
    )

    op.drop_column("task_execution_data", "completion_mode")
