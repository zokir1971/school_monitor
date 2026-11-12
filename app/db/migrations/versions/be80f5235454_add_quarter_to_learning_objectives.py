"""add quarter to learning objectives

Revision ID: be80f5235454
Revises: 7c3df1aea578
Create Date: 2026-09-24 17:26:09.928199

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be80f5235454'
down_revision: Union[str, None] = '7c3df1aea578'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем nullable, потому что таблица уже содержит данные.
    op.add_column(
        "learning_objectives",
        sa.Column(
            "quarter",
            sa.Integer(),
            nullable=True,
        ),
    )

    # 2. Для существующих тестовых данных.
    op.execute(
        """
        UPDATE learning_objectives
        SET quarter = 1
        WHERE quarter IS NULL
        """
    )

    # 3. После заполнения запрещаем NULL.
    op.alter_column(
        "learning_objectives",
        "quarter",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # 4. Constraint 1..4.
    op.create_check_constraint(
        "ck_learning_objectives_quarter",
        "learning_objectives",
        "quarter >= 1 AND quarter <= 4",
    )

    # 5. Старый индекс больше не нужен.
    op.drop_index(
        "ix_learning_objectives_subject_grade_active",
        table_name="learning_objectives",
    )

    # 6. Новый индекс.
    op.create_index(
        "ix_learning_objectives_subject_grade_quarter_active",
        "learning_objectives",
        [
            "subject_id",
            "grade_level",
            "quarter",
            "is_active",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_objectives_subject_grade_quarter_active",
        table_name="learning_objectives",
    )

    op.create_index(
        "ix_learning_objectives_subject_grade_active",
        "learning_objectives",
        [
            "subject_id",
            "grade_level",
            "is_active",
        ],
        unique=False,
    )

    op.drop_constraint(
        "ck_learning_objectives_quarter",
        "learning_objectives",
        type_="check",
    )

    op.drop_column(
        "learning_objectives",
        "quarter",
    )
