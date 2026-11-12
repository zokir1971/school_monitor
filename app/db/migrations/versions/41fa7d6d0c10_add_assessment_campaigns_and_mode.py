"""add assessment campaigns and mode

Revision ID: 41fa7d6d0c10
Revises: eaa3a0589616
Create Date: 2026-08-30 07:36:55.767746

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import context, op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '41fa7d6d0c10'
down_revision: Union[str, None] = 'eaa3a0589616'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ASSESSMENT_MODE_ENUM_NAME = "assessment_mode"

WITHOUT_OBJECTIVES = "without_objectives"
ASSESSMENT_BY_SECTION = "assessment_by_section"
ASSESSMENT_BY_QUARTER = "assessment_by_quarter"


assessment_mode_enum = postgresql.ENUM(
    WITHOUT_OBJECTIVES,
    ASSESSMENT_BY_SECTION,
    ASSESSMENT_BY_QUARTER,
    name=ASSESSMENT_MODE_ENUM_NAME,
)


def upgrade() -> None:
    bind = op.get_bind()

    # =====================================================
    # 1. ENUM
    # =====================================================

    if not context.is_offline_mode():
        assessment_mode_enum.create(
            bind,
            checkfirst=True,
        )
    else:
        op.execute(
            """
            CREATE TYPE assessment_mode AS ENUM (
                'without_objectives',
                'assessment_by_section',
                'assessment_by_quarter'
            )
            """
        )

    # =====================================================
    # 2. ASSESSMENT CAMPAIGNS
    # =====================================================

    op.create_table(
        "assessment_campaigns",

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
            "created_by_user_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "title",
            sa.String(length=255),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "academic_year_start",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),

        sa.UniqueConstraint(
            "id",
            "school_id",
            name="uq_assessment_campaigns_id_school",
        ),

        sa.ForeignKeyConstraint(
            ["school_id"],
            ["schools.id"],
            name="fk_assessment_campaigns_school",
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_assessment_campaigns_created_by",
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_assessment_campaigns_school_year",
        "assessment_campaigns",
        [
            "school_id",
            "academic_year_start",
        ],
        unique=False,
    )

    op.create_index(
        "ix_assessment_campaigns_school_created",
        "assessment_campaigns",
        [
            "school_id",
            "created_at",
        ],
        unique=False,
    )

    # =====================================================
    # 3. ASSESSMENT COLUMNS
    # =====================================================

    op.add_column(
        "assessments",
        sa.Column(
            "campaign_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "assessments",
        sa.Column(
            "assessment_mode",
            assessment_mode_enum,
            nullable=True,
        ),
    )

    op.add_column(
        "assessments",
        sa.Column(
            "duration_minutes",
            sa.SmallInteger(),
            nullable=True,
        ),
    )

    # =====================================================
    # 4. CAMPAIGN FK / INDEX
    # =====================================================

    op.create_foreign_key(
        "fk_assessment_campaign_school",
        "assessments",
        "assessment_campaigns",
        [
            "campaign_id",
            "school_id",
        ],
        [
            "id",
            "school_id",
        ],
        ondelete="RESTRICT",
    )

    op.create_index(
        "ix_assessments_campaign",
        "assessments",
        ["campaign_id"],
        unique=False,
    )

    # =====================================================
    # 5. DURATION CHECK
    # =====================================================

    op.create_check_constraint(
        "ck_assessments_duration_minutes_positive",
        "assessments",
        """
        duration_minutes IS NULL
        OR duration_minutes > 0
        """,
    )

    # =====================================================
    # 6. BACKFILL WITHOUT OBJECTIVES
    # =====================================================

    op.execute(
        """
        UPDATE assessments AS a
        SET assessment_mode = 'without_objectives'
        WHERE NOT EXISTS (
            SELECT 1
            FROM assessment_objectives AS ao
            WHERE ao.assessment_id = a.id
        )
        """
    )

    # =====================================================
    # 7. VERIFY OBJECTIVE-BASED LEGACY DATA
    # =====================================================

    if not context.is_offline_mode():
        unresolved = bind.execute(
            sa.text(
                """
                SELECT
                    a.id,
                    a.title
                FROM assessments AS a
                WHERE a.assessment_mode IS NULL
                ORDER BY a.id
                """
            )
        ).all()

        if unresolved:
            details = ", ".join(
                f"{row.id} ({row.title})"
                for row in unresolved
            )

            raise RuntimeError(
                "Migration stopped. "
                "Existing Assessment with learning objectives "
                "must be explicitly classified as "
                "assessment_by_section or "
                "assessment_by_quarter. "
                f"Unresolved: {details}"
            )

    # =====================================================
    # 8. NOT NULL
    # =====================================================

    op.alter_column(
        "assessments",
        "assessment_mode",
        existing_type=assessment_mode_enum,
        nullable=False,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_assessments_duration_minutes_positive",
        "assessments",
        type_="check",
    )

    op.drop_index(
        "ix_assessments_campaign",
        table_name="assessments",
    )

    op.drop_constraint(
        "fk_assessment_campaign_school",
        "assessments",
        type_="foreignkey",
    )

    op.drop_column(
        "assessments",
        "duration_minutes",
    )

    op.drop_column(
        "assessments",
        "assessment_mode",
    )

    op.drop_column(
        "assessments",
        "campaign_id",
    )

    op.drop_index(
        "ix_assessment_campaigns_school_created",
        table_name="assessment_campaigns",
    )

    op.drop_index(
        "ix_assessment_campaigns_school_year",
        table_name="assessment_campaigns",
    )

    op.drop_table(
        "assessment_campaigns"
    )

    if not context.is_offline_mode():
        assessment_mode_enum.drop(
            op.get_bind(),
            checkfirst=True,
        )
    else:
        op.execute(
            "DROP TYPE assessment_mode"
        )
