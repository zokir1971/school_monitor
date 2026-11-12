"""add assessment checkpoints

Revision ID: 2ba82b26270d
Revises: 41fa7d6d0c10
Create Date: 2026-09-07 22:06:17.436893

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '2ba82b26270d'
down_revision: Union[str, None] = '41fa7d6d0c10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


"""add assessment checkpoints

Revision ID: KEEP_GENERATED_REVISION
Revises: KEEP_GENERATED_DOWN_REVISION
Create Date: KEEP_GENERATED_DATE
"""


# =========================================================
# POSTGRESQL ENUM
# =========================================================

assessment_checkpoint_enum = postgresql.ENUM(
    "baseline",
    "quarter_1",
    "quarter_2",
    "quarter_3",
    "quarter_4",
    "final",
    name="assessment_checkpoint",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # -----------------------------------------------------
    # 1. ENUM TYPE
    # -----------------------------------------------------
    #
    # checkfirst=True:
    #   - создаст тип, если его ещё нет;
    #   - не упадёт с DuplicateObject, если тип уже существует.
    #
    # create_type=False у объекта enum не позволяет
    # add_column повторно выполнять CREATE TYPE.
    #
    assessment_checkpoint_enum.create(
        bind,
        checkfirst=True,
    )

    # -----------------------------------------------------
    # 2. ASSESSMENT
    # -----------------------------------------------------

    op.add_column(
        "assessments",
        sa.Column(
            "checkpoint",
            assessment_checkpoint_enum,
            nullable=True,
        ),
    )

    # -----------------------------------------------------
    # 3. QUALITY SUMMARY SNAPSHOT
    # -----------------------------------------------------

    op.add_column(
        "assessment_quality_summaries",
        sa.Column(
            "checkpoint_snapshot",
            assessment_checkpoint_enum,
            nullable=True,
        ),
    )

    # -----------------------------------------------------
    # 4. DYNAMICS INDEXES
    # -----------------------------------------------------

    op.create_index(
        "ix_assessment_quality_school_dynamics",
        "assessment_quality_summaries",
        [
            "school_id",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
            "checkpoint_snapshot",
        ],
        unique=False,
    )

    op.create_index(
        "ix_assessment_quality_district_dynamics",
        "assessment_quality_summaries",
        [
            "district_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
            "checkpoint_snapshot",
        ],
        unique=False,
    )

    op.create_index(
        "ix_assessment_quality_region_dynamics",
        "assessment_quality_summaries",
        [
            "region_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
            "checkpoint_snapshot",
        ],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    # -----------------------------------------------------
    # 1. INDEXES
    # -----------------------------------------------------

    op.drop_index(
        "ix_assessment_quality_region_dynamics",
        table_name="assessment_quality_summaries",
    )

    op.drop_index(
        "ix_assessment_quality_district_dynamics",
        table_name="assessment_quality_summaries",
    )

    op.drop_index(
        "ix_assessment_quality_school_dynamics",
        table_name="assessment_quality_summaries",
    )

    # -----------------------------------------------------
    # 2. COLUMNS
    # -----------------------------------------------------

    op.drop_column(
        "assessment_quality_summaries",
        "checkpoint_snapshot",
    )

    op.drop_column(
        "assessments",
        "checkpoint",
    )

    # -----------------------------------------------------
    # 3. ENUM TYPE
    # -----------------------------------------------------
    #
    # Тип удаляем только после колонок,
    # которые его используют.
    #
    assessment_checkpoint_enum.drop(
        bind,
        checkfirst=True,
    )
