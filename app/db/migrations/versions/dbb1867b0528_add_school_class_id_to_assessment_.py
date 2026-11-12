"""add school class id to assessment quality summaries

Revision ID: dbb1867b0528
Revises: 7d95c9bc3621
Create Date: 2026-08-25 19:07:18.998131

"""
from __future__ import annotations

from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = 'dbb1867b0528'
down_revision: Union[str, None] = '7d95c9bc3621'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_NAME = "assessment_quality_summaries"

COLUMN_NAME = "school_class_id"

INDEX_NAME = (
    "ix_assessment_quality_summaries_school_class"
)


def upgrade() -> None:
    # =====================================================
    # 1. Добавляем колонку временно nullable
    # =====================================================

    op.add_column(
        TABLE_NAME,
        sa.Column(
            COLUMN_NAME,
            sa.Integer(),
            nullable=True,
        ),
    )

    # =====================================================
    # 2. Backfill из AssessmentGroup
    # =====================================================

    op.execute(
        """
        UPDATE assessment_quality_summaries AS aqs
        SET school_class_id = ag.school_class_id
        FROM assessment_groups AS ag
        WHERE
            ag.id = aqs.assessment_group_id
            AND ag.school_id = aqs.school_id
            AND aqs.school_class_id IS NULL
        """
    )

    # =====================================================
    # 3. Online-проверка
    #
    # В offline --sql реальной БД нет, поэтому
    # scalar_one() выполнять нельзя.
    # =====================================================

    if not context.is_offline_mode():
        connection = op.get_bind()

        missing_count = connection.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM assessment_quality_summaries
                WHERE school_class_id IS NULL
                """
            )
        ).scalar_one()

        if missing_count:
            raise RuntimeError(
                "Migration aborted: "
                f"{missing_count} "
                "assessment_quality_summaries rows "
                "could not resolve school_class_id "
                "from assessment_groups."
            )

    # =====================================================
    # 4. Теперь колонка обязательна
    # =====================================================

    op.alter_column(
        TABLE_NAME,
        COLUMN_NAME,
        existing_type=sa.Integer(),
        nullable=False,
    )

    # =====================================================
    # 5. Индекс
    # =====================================================

    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        [
            COLUMN_NAME,
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        INDEX_NAME,
        table_name=TABLE_NAME,
    )

    op.drop_column(
        TABLE_NAME,
        COLUMN_NAME,
    )
