"""optimize school method associations

Revision ID: 036f605d67b8
Revises: 1cc111585f12
Create Date: 2026-07-29 10:32:37.860704

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '036f605d67b8'
down_revision: Union[str, None] = '1cc111585f12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

"""Optimize school method associations.

Revision ID: replace_with_revision_id
Revises: replace_with_previous_revision_id
Create Date: 2026-07-29

"""


def upgrade() -> None:
    """
    Усиливает целостность таблицы методических объединений
    и удаляет дублирующие индексы.
    """

    # ------------------------------------------------------------------
    # 1. Проверяем, что code заполнен у всех существующих записей.
    #
    # Лучше остановить миграцию с понятным сообщением, чем автоматически
    # генерировать неправильные бизнес-коды.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM school_method_associations
                    WHERE code IS NULL
                       OR btrim(code) = ''
                ) THEN
                    RAISE EXCEPTION
                        'Migration aborted: '
                        'school_method_associations contains NULL or empty codes';
                END IF;
            END
            $$;
            """
        )
    )

    # ------------------------------------------------------------------
    # 2. Проверяем отсутствие одинаковых кодов в пределах одной школы.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM school_method_associations
                    GROUP BY school_id, code
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'Migration aborted: duplicate method association codes '
                        'exist within the same school';
                END IF;
            END
            $$;
            """
        )
    )

    # ------------------------------------------------------------------
    # 3. Делаем code обязательным.
    # ------------------------------------------------------------------
    op.alter_column(
        "school_method_associations",
        "code",
        existing_type=sa.String(length=100),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # 4. Запрещаем повтор одного кода в одной школе.
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        "uq_school_method_association_school_code",
        "school_method_associations",
        [
            "school_id",
            "code",
        ],
    )

    # ------------------------------------------------------------------
    # 5. Удаляем отдельный индекс по булевому полю is_active.
    #
    # Для основных запросов уже существует составной индекс:
    # (school_id, is_active).
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS ix_school_method_associations_is_active
            """
        )
    )

    # ------------------------------------------------------------------
    # 6. Удаляем отдельный индекс method_association_id.
    #
    # Составной индекс
    # (method_association_id, protocol_date)
    # может использоваться PostgreSQL и для фильтрации только по
    # method_association_id.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS ix_school_task_reviews_method_association_id
            """
        )
    )


def downgrade() -> None:
    """
    Возвращает предыдущую структуру таблиц.
    """

    # Восстанавливаем отдельный индекс внешнего ключа.
    op.create_index(
        "ix_school_task_reviews_method_association_id",
        "school_task_reviews",
        ["method_association_id"],
        unique=False,
    )

    # Восстанавливаем отдельный индекс по is_active.
    op.create_index(
        "ix_school_method_associations_is_active",
        "school_method_associations",
        ["is_active"],
        unique=False,
    )

    # Удаляем уникальность кода внутри школы.
    op.drop_constraint(
        "uq_school_method_association_school_code",
        "school_method_associations",
        type_="unique",
    )

    # Снова разрешаем NULL.
    op.alter_column(
        "school_method_associations",
        "code",
        existing_type=sa.String(length=100),
        nullable=True,
    )
