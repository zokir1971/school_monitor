"""add template schema and lesson criteria scores

Revision ID: 03d6d7230b1f
Revises: b5e90c25898e
Create Date: 2026-04-28 09:51:35.755565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '03d6d7230b1f'
down_revision: Union[str, None] = 'b5e90c25898e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "user_report_templates",
        sa.Column(
            "schema_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.add_column(
        "lesson_observation_reports",
        sa.Column(
            "criteria_scores",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("lesson_observation_reports", "criteria_scores")
    op.drop_column("user_report_templates", "schema_json")
