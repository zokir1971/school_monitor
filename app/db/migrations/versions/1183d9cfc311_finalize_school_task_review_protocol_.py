"""finalize school task review protocol identity

Revision ID: 1183d9cfc311
Revises: 13aa5a889a9c
Create Date: 2026-07-29 12:02:45.766469
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1183d9cfc311"
down_revision: Union[str, None] = "13aa5a889a9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "school_task_reviews"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Переносим старую дату рассмотрения в дату протокола.
    #
    # По бизнес-логике review_date и protocol_date означают одну дату.
    # Заполняем protocol_date только там, где она ещё отсутствует.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            UPDATE school_task_reviews
            SET protocol_date = review_date
            WHERE protocol_date IS NULL
              AND review_date IS NOT NULL
            """
        )
    )

    # ------------------------------------------------------------------
    # 2. Нормализуем номера протоколов.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            UPDATE school_task_reviews
            SET protocol_number = btrim(protocol_number)
            WHERE protocol_number IS NOT NULL
            """
        )
    )

    # ------------------------------------------------------------------
    # 3. Проверяем обязательные данные.
    #
    # Номер протокола невозможно безопасно восстановить автоматически,
    # поэтому при наличии пустых значений миграция должна остановиться.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM school_task_reviews
                    WHERE protocol_number IS NULL
                       OR btrim(protocol_number) = ''
                ) THEN
                    RAISE EXCEPTION
                        'Migration aborted: school_task_reviews contains '
                        'NULL or empty protocol_number values';
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM school_task_reviews
                    WHERE protocol_date IS NULL
                ) THEN
                    RAISE EXCEPTION
                        'Migration aborted: school_task_reviews contains '
                        'NULL protocol_date values';
                END IF;
            END
            $$;
            """
        )
    )

    # ------------------------------------------------------------------
    # 4. Проверяем согласованность места рассмотрения и МО.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM school_task_reviews
                    WHERE (
                        review_place = 'method_assoc'
                        AND method_association_id IS NULL
                    )
                    OR (
                        review_place <> 'method_assoc'
                        AND method_association_id IS NOT NULL
                    )
                ) THEN
                    RAISE EXCEPTION
                        'Migration aborted: inconsistent review_place '
                        'and method_association_id values exist';
                END IF;
            END
            $$;
            """
        )
    )

    # ------------------------------------------------------------------
    # 5. Проверяем дубликаты обычных протоколов.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM school_task_reviews
                    WHERE method_association_id IS NULL
                    GROUP BY
                        school_plan_id,
                        review_place,
                        protocol_number,
                        protocol_date
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'Migration aborted: duplicate general protocols exist';
                END IF;
            END
            $$;
            """
        )
    )

    # ------------------------------------------------------------------
    # 6. Проверяем дубликаты протоколов методических объединений.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM school_task_reviews
                    WHERE method_association_id IS NOT NULL
                    GROUP BY
                        school_plan_id,
                        review_place,
                        method_association_id,
                        protocol_number,
                        protocol_date
                    HAVING COUNT(*) > 1
                ) THEN
                    RAISE EXCEPTION
                        'Migration aborted: duplicate method association '
                        'protocols exist';
                END IF;
            END
            $$;
            """
        )
    )

    # ------------------------------------------------------------------
    # 7. Удаляем старые и возможные ранее созданные индексы.
    #
    # Используем IF EXISTS, чтобы миграция была устойчивой к отличиям
    # локальной и серверной схемы.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                ix_school_task_reviews_plan_place_date
            """
        )
    )

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                ix_school_task_reviews_method_assoc_review_date
            """
        )
    )

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                ix_school_task_reviews_method_assoc_protocol_date
            """
        )
    )

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                uq_school_task_reviews_protocol_identity_general
            """
        )
    )

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                uq_school_task_reviews_protocol_identity_method_assoc
            """
        )
    )

    # ------------------------------------------------------------------
    # 8. Делаем номер и дату протокола обязательными.
    # ------------------------------------------------------------------
    op.alter_column(
        TABLE_NAME,
        "protocol_number",
        existing_type=sa.String(length=100),
        nullable=False,
    )

    op.alter_column(
        TABLE_NAME,
        "protocol_date",
        existing_type=sa.Date(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # 9. Удаляем устаревшую колонку review_date.
    # ------------------------------------------------------------------
    op.drop_column(
        TABLE_NAME,
        "review_date",
    )

    # ------------------------------------------------------------------
    # 10. Создаём или пересоздаём ограничение номера протокола.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            ALTER TABLE school_task_reviews
            DROP CONSTRAINT IF EXISTS
                ck_school_task_reviews_protocol_number_not_blank
            """
        )
    )

    op.create_check_constraint(
        "ck_school_task_reviews_protocol_number_not_blank",
        TABLE_NAME,
        "btrim(protocol_number) <> ''",
    )

    # ------------------------------------------------------------------
    # 11. Гарантируем согласованность method_association_id.
    #
    # Ограничение добавляется только в случае его отсутствия.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname =
                        'ck_school_task_review_method_association'
                      AND conrelid =
                        'school_task_reviews'::regclass
                ) THEN
                    ALTER TABLE school_task_reviews
                    ADD CONSTRAINT
                        ck_school_task_review_method_association
                    CHECK (
                        (
                            review_place = 'method_assoc'
                            AND method_association_id IS NOT NULL
                        )
                        OR
                        (
                            review_place <> 'method_assoc'
                            AND method_association_id IS NULL
                        )
                    );
                END IF;
            END
            $$;
            """
        )
    )

    # ------------------------------------------------------------------
    # 12. Основной индекс для выборки протоколов плана.
    # ------------------------------------------------------------------
    op.create_index(
        "ix_school_task_reviews_plan_place_date",
        TABLE_NAME,
        [
            "school_plan_id",
            "review_place",
            "protocol_date",
        ],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 13. Индекс истории конкретного методического объединения.
    # ------------------------------------------------------------------
    op.create_index(
        "ix_school_task_reviews_method_assoc_protocol_date",
        TABLE_NAME,
        [
            "method_association_id",
            "protocol_date",
        ],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 14. Уникальность обычных протоколов.
    # ------------------------------------------------------------------
    op.create_index(
        "uq_school_task_reviews_protocol_identity_general",
        TABLE_NAME,
        [
            "school_plan_id",
            "review_place",
            "protocol_number",
            "protocol_date",
        ],
        unique=True,
        postgresql_where=sa.text(
            "method_association_id IS NULL"
        ),
    )

    # ------------------------------------------------------------------
    # 15. Уникальность протоколов методических объединений.
    # ------------------------------------------------------------------
    op.create_index(
        "uq_school_task_reviews_protocol_identity_method_assoc",
        TABLE_NAME,
        [
            "school_plan_id",
            "review_place",
            "method_association_id",
            "protocol_number",
            "protocol_date",
        ],
        unique=True,
        postgresql_where=sa.text(
            "method_association_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Удаляем новые индексы.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                uq_school_task_reviews_protocol_identity_method_assoc
            """
        )
    )

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                uq_school_task_reviews_protocol_identity_general
            """
        )
    )

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                ix_school_task_reviews_method_assoc_protocol_date
            """
        )
    )

    op.execute(
        sa.text(
            """
            DROP INDEX IF EXISTS
                ix_school_task_reviews_plan_place_date
            """
        )
    )

    # ------------------------------------------------------------------
    # 2. Удаляем ограничение непустого номера.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            """
            ALTER TABLE school_task_reviews
            DROP CONSTRAINT IF EXISTS
                ck_school_task_reviews_protocol_number_not_blank
            """
        )
    )

    # ------------------------------------------------------------------
    # 3. Возвращаем старую колонку review_date.
    # ------------------------------------------------------------------
    op.add_column(
        TABLE_NAME,
        sa.Column(
            "review_date",
            sa.Date(),
            nullable=True,
        ),
    )

    # По старой бизнес-логике даты были одинаковыми.
    op.execute(
        sa.text(
            """
            UPDATE school_task_reviews
            SET review_date = protocol_date
            """
        )
    )

    op.alter_column(
        TABLE_NAME,
        "review_date",
        existing_type=sa.Date(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # 4. Возвращаем nullable для старой схемы.
    # ------------------------------------------------------------------
    op.alter_column(
        TABLE_NAME,
        "protocol_date",
        existing_type=sa.Date(),
        nullable=True,
    )

    op.alter_column(
        TABLE_NAME,
        "protocol_number",
        existing_type=sa.String(length=100),
        nullable=True,
    )

    # ------------------------------------------------------------------
    # 5. Возвращаем старые индексы.
    # ------------------------------------------------------------------
    op.create_index(
        "ix_school_task_reviews_plan_place_date",
        TABLE_NAME,
        [
            "school_plan_id",
            "review_place",
            "review_date",
        ],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_method_assoc_review_date",
        TABLE_NAME,
        [
            "method_association_id",
            "review_date",
        ],
        unique=False,
    )
