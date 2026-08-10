"""optimize task review indexes

Revision ID: 13aa5a889a9c
Revises: 036f605d67b8
Create Date: 2026-07-29 10:56:13.708985

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '13aa5a889a9c'
down_revision: Union[str, None] = '036f605d67b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # SchoolMethodAssociation
    # ---------------------------------------------------------------

    # Удаляем обычный составной индекс.
    op.drop_index(
        "ix_school_method_associations_school_active",
        table_name="school_method_associations",
    )

    # Удаляем дублирующий индекс school_id.
    op.drop_index(
        "ix_school_method_associations_school_id",
        table_name="school_method_associations",
    )

    # Создаём частичный индекс только для активных МО.
    # Он поддерживает одновременно:
    #   WHERE school_id = ?
    #   AND is_active IS TRUE
    #   ORDER BY name
    op.execute(
        """
        CREATE INDEX ix_school_method_associations_active_school_name
        ON school_method_associations (school_id, name)
        WHERE is_active IS TRUE
        """
    )

    # ---------------------------------------------------------------
    # SchoolTaskReview
    # ---------------------------------------------------------------

    # Старый индекс использует protocol_date,
    # но история заседаний должна сортироваться по review_date.
    op.drop_index(
        "ix_school_task_reviews_method_association",
        table_name="school_task_reviews",
    )

    op.create_index(
        "ix_school_task_reviews_method_assoc_review_date",
        "school_task_reviews",
        [
            "method_association_id",
            "review_date",
        ],
        unique=False,
    )

    # Эти индексы покрываются составными индексами
    # или обладают слишком низкой селективностью.
    op.drop_index(
        "ix_school_task_reviews_school_plan_id",
        table_name="school_task_reviews",
    )

    op.drop_index(
        "ix_school_task_reviews_review_place",
        table_name="school_task_reviews",
    )

    op.drop_index(
        "ix_school_task_reviews_review_date",
        table_name="school_task_reviews",
    )


def downgrade() -> None:
    # ---------------------------------------------------------------
    # SchoolTaskReview
    # ---------------------------------------------------------------

    op.create_index(
        "ix_school_task_reviews_review_date",
        "school_task_reviews",
        ["review_date"],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_review_place",
        "school_task_reviews",
        ["review_place"],
        unique=False,
    )

    op.create_index(
        "ix_school_task_reviews_school_plan_id",
        "school_task_reviews",
        ["school_plan_id"],
        unique=False,
    )

    op.drop_index(
        "ix_school_task_reviews_method_assoc_review_date",
        table_name="school_task_reviews",
    )

    op.create_index(
        "ix_school_task_reviews_method_association",
        "school_task_reviews",
        [
            "method_association_id",
            "protocol_date",
        ],
        unique=False,
    )

    # ---------------------------------------------------------------
    # SchoolMethodAssociation
    # ---------------------------------------------------------------

    op.drop_index(
        "ix_school_method_associations_active_school_name",
        table_name="school_method_associations",
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
        [
            "school_id",
            "is_active",
        ],
        unique=False,
    )
