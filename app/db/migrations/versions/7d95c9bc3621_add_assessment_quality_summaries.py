"""add assessment quality summaries

Revision ID: 7d95c9bc3621
Revises: bd41a9903310
Create Date: 2026-08-25 06:13:40.344886

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d95c9bc3621'
down_revision: Union[str, None] = 'bd41a9903310'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "assessment_quality_summaries"


def upgrade() -> None:
    op.create_table(
        TABLE_NAME,

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
        ),

        sa.Column(
            "school_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "assessment_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "assessment_group_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "subject_id",
            sa.Integer(),
            nullable=False,
        ),

        # -------------------------------------------------
        # ORGANIZATION SNAPSHOT
        # -------------------------------------------------

        sa.Column(
            "district_id_snapshot",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "region_id_snapshot",
            sa.Integer(),
            nullable=True,
        ),

        # -------------------------------------------------
        # CLASS SNAPSHOT
        # -------------------------------------------------

        sa.Column(
            "class_name_snapshot",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "grade_level_snapshot",
            sa.SmallInteger(),
            nullable=False,
        ),

        sa.Column(
            "academic_year_start_snapshot",
            sa.Integer(),
            nullable=False,
        ),

        # -------------------------------------------------
        # PARTICIPATION
        # -------------------------------------------------

        sa.Column(
            "total_students",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "participated_students",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "absent_students",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "excused_students",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "not_completed_students",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        # -------------------------------------------------
        # GRADES
        # -------------------------------------------------

        sa.Column(
            "grade_5_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "grade_4_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "grade_3_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "grade_2_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        # -------------------------------------------------
        # AGGREGATE VALUES
        # -------------------------------------------------

        sa.Column(
            "score_sum",
            sa.Numeric(
                precision=14,
                scale=4,
            ),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "percent_sum",
            sa.Numeric(
                precision=16,
                scale=4,
            ),
            nullable=False,
            server_default="0",
        ),

        # -------------------------------------------------
        # INDICATORS
        # -------------------------------------------------

        sa.Column(
            "average_score",
            sa.Numeric(
                precision=10,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "average_percent",
            sa.Numeric(
                precision=7,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "achievement_percent",
            sa.Numeric(
                precision=7,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "quality_percent",
            sa.Numeric(
                precision=7,
                scale=2,
            ),
            nullable=True,
        ),

        # -------------------------------------------------
        # AUDIT
        # -------------------------------------------------

        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
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

        # -------------------------------------------------
        # CONSTRAINTS
        # -------------------------------------------------

        sa.UniqueConstraint(
            "assessment_group_id",
            name=(
                "uq_assessment_quality_summary_group"
            ),
        ),

        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            name=(
                "fk_assessment_quality_summary_school"
            ),
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=(
                "fk_assessment_quality_summary_subject"
            ),
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            [
                "assessment_id",
                "school_id",
            ],
            [
                "assessments.id",
                "assessments.school_id",
            ],
            name=(
                "fk_assessment_quality_summary_"
                "assessment_school"
            ),
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            [
                "assessment_group_id",
                "school_id",
            ],
            [
                "assessment_groups.id",
                "assessment_groups.school_id",
            ],
            name=(
                "fk_assessment_quality_summary_"
                "group_school"
            ),
            ondelete="CASCADE",
        ),
    )

    # =====================================================
    # INDEXES
    # =====================================================

    op.create_index(
        "ix_assessment_quality_summaries_assessment",
        TABLE_NAME,
        [
            "assessment_id",
        ],
        unique=False,
    )

    op.create_index(
        "ix_assessment_quality_school_year_subject_grade",
        TABLE_NAME,
        [
            "school_id",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
        ],
        unique=False,
    )

    op.create_index(
        "ix_assessment_quality_district_year_subject_grade",
        TABLE_NAME,
        [
            "district_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
        ],
        unique=False,
    )

    op.create_index(
        "ix_assessment_quality_region_year_subject_grade",
        TABLE_NAME,
        [
            "region_id_snapshot",
            "academic_year_start_snapshot",
            "subject_id",
            "grade_level_snapshot",
        ],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assessment_quality_region_year_subject_grade",
        table_name=TABLE_NAME,
    )

    op.drop_index(
        "ix_assessment_quality_district_year_subject_grade",
        table_name=TABLE_NAME,
    )

    op.drop_index(
        "ix_assessment_quality_school_year_subject_grade",
        table_name=TABLE_NAME,
    )

    op.drop_index(
        "ix_assessment_quality_summaries_assessment",
        table_name=TABLE_NAME,
    )

    op.drop_table(
        TABLE_NAME
    )
