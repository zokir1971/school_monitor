"""add teacher snapshot to assessment quality summaries

Revision ID: 704452ea1e37
Revises: dbb1867b0528
Create Date: 2026-08-28 06:24:23.405460

"""
from typing import Sequence, Union

from alembic import op, context
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '704452ea1e37'
down_revision: Union[str, None] = 'dbb1867b0528'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "assessment_quality_summaries"

TEACHER_ID_COLUMN = (
    "teacher_staff_member_id_snapshot"
)

TEACHER_NAME_COLUMN = (
    "teacher_name_snapshot"
)

INDEX_NAME = (
    "ix_assessment_quality_summaries_teacher_analytics"
)


def upgrade() -> None:
    # =====================================================
    # 1. Добавляем nullable snapshot-поля
    # =====================================================

    op.add_column(
        TABLE_NAME,
        sa.Column(
            TEACHER_ID_COLUMN,
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        TABLE_NAME,
        sa.Column(
            TEACHER_NAME_COLUMN,
            sa.String(
                length=255,
            ),
            nullable=True,
        ),
    )

    # =====================================================
    # 2. Backfill из assessment_groups
    # =====================================================

    op.execute(
        """
        UPDATE assessment_quality_summaries AS aqs
        SET
            teacher_staff_member_id_snapshot =
                ag.teacher_staff_member_id,

            teacher_name_snapshot =
                ag.teacher_name_snapshot
        FROM assessment_groups AS ag
        WHERE
            ag.id = aqs.assessment_group_id
            AND ag.school_id = aqs.school_id
        """
    )

    # =====================================================
    # 3. Проверка целостности online-mode
    # =====================================================

    if not context.is_offline_mode():
        connection = op.get_bind()

        unresolved_count = connection.execute(
            sa.text(
                """
                SELECT COUNT(*)
                FROM assessment_quality_summaries AS aqs
                LEFT JOIN assessment_groups AS ag
                    ON ag.id = aqs.assessment_group_id
                    AND ag.school_id = aqs.school_id
                WHERE ag.id IS NULL
                """
            )
        ).scalar_one()

        if unresolved_count:
            raise RuntimeError(
                "Migration aborted: "
                f"{unresolved_count} "
                "assessment_quality_summaries rows "
                "do not have matching assessment_groups."
            )

    # =====================================================
    # 4. Индекс teacher analytics
    # =====================================================

    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        [
            "school_id",
            TEACHER_ID_COLUMN,
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
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
        TEACHER_NAME_COLUMN,
    )

    op.drop_column(
        TABLE_NAME,
        TEACHER_ID_COLUMN,
    )
