"""change report_type to report_types

Revision ID: 14dafbca9bc8
Revises: e4d4a758805d
Create Date: 2026-04-09 19:03:58.324161

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '14dafbca9bc8'
down_revision: Union[str, None] = 'e4d4a758805d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

"""change report_type to report_types

Revision ID: xxxxxxxxxxxx
Revises: previous_revision_id
Create Date: 2026-04-09
"""


def upgrade() -> None:
    op.add_column(
        "school_month_plan_item_executions",
        sa.Column(
            "report_types",
            postgresql.ARRAY(sa.String()),
            nullable=True,
        ),
    )

    op.drop_column("school_month_plan_item_executions", "report_type")


def downgrade() -> None:
    op.add_column(
        "school_month_plan_item_executions",
        sa.Column(
            "report_type",
            sa.String(),
            nullable=True,
        ),
    )
