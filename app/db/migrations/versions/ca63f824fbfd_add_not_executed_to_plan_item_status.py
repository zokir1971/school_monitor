"""add not_executed to plan_item_status

Revision ID: ca63f824fbfd
Revises: e875aff432fe
Create Date: 2026-04-06 22:12:57.970983

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ca63f824fbfd'
down_revision: Union[str, None] = 'e875aff432fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute(
        "ALTER TYPE plan_item_status ADD VALUE IF NOT EXISTS 'not_executed';"
    )


def downgrade():
    # Для PostgreSQL удаление enum-значения отдельно не поддерживается
    pass
