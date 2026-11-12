"""add submitted assessment participation status

Revision ID: 9be11d1036f3
Revises: 2ba82b26270d
Create Date: 2026-09-14 20:24:05.242065

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9be11d1036f3'
down_revision: Union[str, None] = '2ba82b26270d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TYPE assessment_participation_status
        ADD VALUE IF NOT EXISTS 'submitted'
        AFTER 'in_progress'
        """
    )


def downgrade() -> None:
    # PostgreSQL не поддерживает безопасное удаление
    # отдельного значения ENUM через DROP VALUE.
    #
    # Откат потребовал бы пересоздания enum-типа,
    # поэтому здесь намеренно ничего не делаем.
    pass
