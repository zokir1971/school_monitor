"""add accepted to task_document_status_enum

Revision ID: a283836b14d3
Revises: 32bfd7789ef1
Create Date: 2026-04-12 09:49:23.254987

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a283836b14d3'
down_revision: Union[str, None] = '32bfd7789ef1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("ALTER TYPE task_document_status_enum ADD VALUE IF NOT EXISTS 'accepted'")


def downgrade():
    # PostgreSQL не умеет удалять enum значения
    pass
