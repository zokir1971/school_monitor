"""allow june in school month plans

Revision ID: 46d7991e0878
Revises: 1183d9cfc311
Create Date: 2026-08-04 09:29:33.488760

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '46d7991e0878'
down_revision: Union[str, None] = '1183d9cfc311'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_school_month_plans_month_range",
        "school_month_plans",
        type_="check",
    )

    op.create_check_constraint(
        "ck_school_month_plans_month_range",
        "school_month_plans",
        "(month BETWEEN 8 AND 12) OR (month BETWEEN 1 AND 6)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_school_month_plans_month_range",
        "school_month_plans",
        type_="check",
    )

    op.create_check_constraint(
        "ck_school_month_plans_month_range",
        "school_month_plans",
        "(month BETWEEN 9 AND 12) OR (month BETWEEN 1 AND 5)",
    )
