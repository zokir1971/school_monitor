"""add method associations to task reviews

Revision ID: 1cc111585f12
Revises: 6a26dd5e844f
Create Date: 2026-07-28 08:38:35.598409
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1cc111585f12"
down_revision: Union[str, None] = "6a26dd5e844f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Справочник методических объединений школы
    # ------------------------------------------------------------------

    op.create_table(
        "school_method_associations",
        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "school_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=255),
            nullable=False,
        ),
        sa.Column(
            "code",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            name="fk_school_method_associations_school_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_school_method_associations",
        ),
        sa.UniqueConstraint(
            "school_id",
            "name",
            name="uq_school_method_association_school_name",
        ),
    )

    op.create_index(
        "ix_school_method_associations_school_id",
        "school_method_associations",
        ["school_id"],
        unique=False,
    )

    op.create_index(
        "ix_school_method_associations_school_active",
        "school_method_associations",
        ["school_id", "is_active"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 2. Привязка заседания к конкретному МО
    # ------------------------------------------------------------------

    op.add_column(
        "school_task_reviews",
        sa.Column(
            "method_association_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_school_task_reviews_method_association_id",
        "school_task_reviews",
        "school_method_associations",
        ["method_association_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_school_task_reviews_method_association_id",
        "school_task_reviews",
        ["method_association_id"],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_method_association",
        "school_task_reviews",
        ["method_association_id", "protocol_date"],
        unique=False,
    )

    # Для заседания МО конкретное объединение обязательно.
    # Для остальных мест рассмотрения поле должно оставаться NULL.
    op.create_check_constraint(
        "ck_school_task_review_method_association",
        "school_task_reviews",
        """
        (
            review_place = 'method_assoc'
            AND method_association_id IS NOT NULL
        )
        OR
        (
            review_place <> 'method_assoc'
            AND method_association_id IS NULL
        )
        """,
    )

    # ------------------------------------------------------------------
    # 3. Привязка результата задачи к конкретному рассмотрению
    # ------------------------------------------------------------------

    op.add_column(
        "school_month_plan_item_review_results",
        sa.Column(
            "task_review_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_foreign_key(
        "fk_review_results_task_review_id",
        "school_month_plan_item_review_results",
        "school_task_reviews",
        ["task_review_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_review_result_task_review",
        "school_month_plan_item_review_results",
        ["task_review_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # 4. Заполнение task_review_id у существующих результатов
    #
    # Это одноразовое сопоставление старых данных:
    # result.protocol_document_id
    #     -> task_execution_documents.file_path
    #     -> school_task_reviews.protocol_file_path
    # ------------------------------------------------------------------

    op.execute(
        """
        UPDATE school_month_plan_item_review_results AS result
        SET task_review_id = (
            SELECT review.id
            FROM task_execution_documents AS document
            JOIN school_task_reviews AS review
              ON review.protocol_file_path = document.file_path
            WHERE document.id = result.protocol_document_id
              AND review.review_place = result.review_place
            ORDER BY review.id DESC
            LIMIT 1
        )
        WHERE result.task_review_id IS NULL;
        """
    )

    # ------------------------------------------------------------------
    # 5. Проверка заполнения старых данных
    # ------------------------------------------------------------------

    op.execute(
        """
        DO $$
        DECLARE
            missing_count integer;
        BEGIN
            SELECT COUNT(*)
            INTO missing_count
            FROM school_month_plan_item_review_results
            WHERE task_review_id IS NULL;

            IF missing_count > 0 THEN
                RAISE EXCEPTION
                    'Не удалось заполнить task_review_id для % '
                    'результатов рассмотрения. Проверьте соответствие '
                    'task_execution_documents.file_path и '
                    'school_task_reviews.protocol_file_path.',
                    missing_count;
            END IF;
        END
        $$;
        """
    )

    op.alter_column(
        "school_month_plan_item_review_results",
        "task_review_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # ------------------------------------------------------------------
    # 6. Удаление старой уникальности
    #
    # Старая уникальность:
    # month_item_id + review_place
    #
    # Она запрещает одной задаче участвовать в заседаниях нескольких МО.
    # ------------------------------------------------------------------

    op.drop_constraint(
        "uq_month_item_review_result_place",
        "school_month_plan_item_review_results",
        type_="unique",
    )

    op.drop_index(
        "ix_review_result_month_item_place_status",
        table_name="school_month_plan_item_review_results",
    )

    # ------------------------------------------------------------------
    # 7. Новая уникальность
    #
    # Одна задача может присутствовать только один раз
    # внутри одного конкретного рассмотрения.
    # ------------------------------------------------------------------

    op.create_unique_constraint(
        "uq_review_result_month_item_task_review",
        "school_month_plan_item_review_results",
        [
            "month_item_id",
            "task_review_id",
        ],
    )

    op.create_index(
        "ix_review_result_month_item_status",
        "school_month_plan_item_review_results",
        [
            "month_item_id",
            "status",
        ],
        unique=False,
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Проверка возможности возврата к старой уникальности
    # ------------------------------------------------------------------

    op.execute(
        """
        DO $$
        DECLARE
            duplicate_count integer;
        BEGIN
            SELECT COUNT(*)
            INTO duplicate_count
            FROM (
                SELECT
                    month_item_id,
                    review_place
                FROM school_month_plan_item_review_results
                GROUP BY
                    month_item_id,
                    review_place
                HAVING COUNT(*) > 1
            ) AS duplicates;

            IF duplicate_count > 0 THEN
                RAISE EXCEPTION
                    'Downgrade невозможен: найдено % сочетаний '
                    'month_item_id + review_place с несколькими '
                    'результатами рассмотрения.',
                    duplicate_count;
            END IF;
        END
        $$;
        """
    )

    # ------------------------------------------------------------------
    # 2. Возврат старой структуры результата рассмотрения
    # ------------------------------------------------------------------

    op.drop_index(
        "ix_review_result_month_item_status",
        table_name="school_month_plan_item_review_results",
    )

    op.drop_constraint(
        "uq_review_result_month_item_task_review",
        "school_month_plan_item_review_results",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_month_item_review_result_place",
        "school_month_plan_item_review_results",
        [
            "month_item_id",
            "review_place",
        ],
    )

    op.create_index(
        "ix_review_result_month_item_place_status",
        "school_month_plan_item_review_results",
        [
            "month_item_id",
            "review_place",
            "status",
        ],
        unique=False,
    )

    op.drop_index(
        "ix_review_result_task_review",
        table_name="school_month_plan_item_review_results",
    )

    op.drop_constraint(
        "fk_review_results_task_review_id",
        "school_month_plan_item_review_results",
        type_="foreignkey",
    )

    op.drop_column(
        "school_month_plan_item_review_results",
        "task_review_id",
    )

    # ------------------------------------------------------------------
    # 3. Удаление связи с конкретным МО
    # ------------------------------------------------------------------

    op.drop_constraint(
        "ck_school_task_review_method_association",
        "school_task_reviews",
        type_="check",
    )

    op.drop_index(
        "ix_school_task_reviews_method_association",
        table_name="school_task_reviews",
    )

    op.drop_index(
        "ix_school_task_reviews_method_association_id",
        table_name="school_task_reviews",
    )

    op.drop_constraint(
        "fk_school_task_reviews_method_association_id",
        "school_task_reviews",
        type_="foreignkey",
    )

    op.drop_column(
        "school_task_reviews",
        "method_association_id",
    )

    # ------------------------------------------------------------------
    # 4. Удаление справочника МО
    # ------------------------------------------------------------------

    op.drop_index(
        "ix_school_method_associations_school_active",
        table_name="school_method_associations",
    )

    op.drop_index(
        "ix_school_method_associations_school_id",
        table_name="school_method_associations",
    )

    op.drop_table("school_method_associations")
