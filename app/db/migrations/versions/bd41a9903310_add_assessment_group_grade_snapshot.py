"""add assessment group grade snapshot

Revision ID: bd41a9903310
Revises: b1f911d26c7b
Create Date: 2026-08-22 21:39:02.312284

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd41a9903310'
down_revision: Union[str, None] = 'b1f911d26c7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "assessment_groups"

COLUMN_NAME = "grade_level_snapshot"

INDEX_NAME = (
    "ix_assessment_groups_school_grade"
)


def upgrade() -> None:
    # =====================================================
    # 1. Добавляем колонку временно nullable
    # =====================================================

    op.add_column(
        TABLE_NAME,
        sa.Column(
            COLUMN_NAME,
            sa.SmallInteger(),
            nullable=True,
        ),
    )

    # =====================================================
    # 2. Заполняем существующие AssessmentGroup
    #    из SchoolClass
    # =====================================================

    op.execute(
        """
        UPDATE assessment_groups AS ag
        SET grade_level_snapshot = sc.grade_level
        FROM school_classes AS sc
        WHERE
            sc.id = ag.school_class_id
            AND sc.school_id = ag.school_id
            AND ag.grade_level_snapshot IS NULL
        """
    )

    # =====================================================
    # 3. Защитная проверка
    #
    # Если хотя бы одна старая строка не смогла получить
    # grade_level, миграцию останавливаем.
    # Никакие данные не удаляем.
    # =====================================================

    if not context.is_offline_mode():
        connection = op.get_bind()

        missing_count = connection.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM assessment_groups
                WHERE grade_level_snapshot IS NULL
                """
            )
        ).scalar_one()

        if missing_count:
            raise RuntimeError(
                "Migration aborted: "
                f"{missing_count} assessment_groups rows "
                "could not resolve grade_level_snapshot "
                "from school_classes."
            )
    # =====================================================
    # 4. Теперь безопасно включаем NOT NULL
    # =====================================================

    op.alter_column(
        TABLE_NAME,
        COLUMN_NAME,
        existing_type=sa.SmallInteger(),
        nullable=False,
    )

    # =====================================================
    # 5. Индекс для фильтрации школа + параллель
    # =====================================================

    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        [
            "school_id",
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
