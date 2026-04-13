"""fix task_execution_documents timestamps defaults

Revision ID: 82e17f0ff91e
Revises: 95c48482b46e
Create Date: 2026-04-13 09:01:47.325337

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82e17f0ff91e'
down_revision: Union[str, None] = '95c48482b46e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Устанавливаем default now() для created_at
    op.alter_column(
        "task_execution_documents",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )

    # Устанавливаем default now() для updated_at
    op.alter_column(
        "task_execution_documents",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Убираем default (если откат)
    op.alter_column(
        "task_execution_documents",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "task_execution_documents",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )
