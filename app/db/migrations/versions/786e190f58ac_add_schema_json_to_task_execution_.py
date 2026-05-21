"""add schema_json to task_execution_documents

Revision ID: 786e190f58ac
Revises: 03d6d7230b1f
Create Date: 2026-04-28 20:43:40.194490

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '786e190f58ac'
down_revision: Union[str, None] = '03d6d7230b1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task_execution_documents",
        sa.Column(
            "schema_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("task_execution_documents", "schema_json")
