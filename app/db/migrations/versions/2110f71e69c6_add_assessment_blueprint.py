"""add assessment blueprint

Revision ID: 2110f71e69c6
Revises: 9be11d1036f3
Create Date: 2026-09-19 10:07:10.985808
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "2110f71e69c6"
down_revision: Union[str, None] = "9be11d1036f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =========================================================
# POSTGRESQL ENUMS
# =========================================================

assessment_language_enum = postgresql.ENUM(
    "kk",
    "ru",
    "en",
    name="assessment_language",
    create_type=False,
)

assessment_blueprint_status_enum = postgresql.ENUM(
    "draft",
    "ready",
    "archived",
    name="assessment_blueprint_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # =====================================================
    # ENUM TYPES
    # =====================================================

    assessment_language_enum.create(
        bind,
        checkfirst=True,
    )

    assessment_blueprint_status_enum.create(
        bind,
        checkfirst=True,
    )

    # =====================================================
    # ASSESSMENT BLUEPRINT
    # =====================================================

    op.create_table(
        "assessment_blueprints",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "grade_level",
            sa.SmallInteger(),
            nullable=False,
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
            "assessment_type",
            postgresql.ENUM(
                "diagnostic",
                "monitoring",
                "control",
                "summative",
                "custom",
                name="assessment_type",
                create_type=False,
            ),
            nullable=False,
        ),

        sa.Column(
            "assessment_mode",
            postgresql.ENUM(
                "without_objectives",
                "assessment_by_section",
                "assessment_by_quarter",
                name="assessment_mode",
                create_type=False,
            ),
            nullable=False,
        ),

        sa.Column(
            "language",
            assessment_language_enum,
            nullable=False,
        ),

        sa.Column(
            "status",
            assessment_blueprint_status_enum,
            nullable=False,
        ),

        sa.Column(
            "question_count",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "max_score",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column(
            "duration_minutes",
            sa.SmallInteger(),
            nullable=True,
        ),

        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),

        sa.Column(
            "created_by_user_id",
            sa.Integer(),
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

        sa.CheckConstraint(
            "duration_minutes IS NULL OR duration_minutes > 0",
            name="ck_assessment_blueprints_duration_minutes_positive",
        ),
        sa.CheckConstraint(
            "grade_level BETWEEN 1 AND 12",
            name="ck_assessment_blueprints_grade_level",
        ),
        sa.CheckConstraint(
            "max_score > 0",
            name="ck_assessment_blueprints_max_score_positive",
        ),
        sa.CheckConstraint(
            "question_count > 0",
            name="ck_assessment_blueprints_question_count_positive",
        ),

        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name="fk_assessment_blueprints_creator",
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name="fk_assessment_blueprints_subject",
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_assessment_blueprints_creator",
        "assessment_blueprints",
        ["created_by_user_id"],
        unique=False,
    )

    op.create_index(
        "ix_assessment_blueprints_subject_grade_status",
        "assessment_blueprints",
        ["subject_id", "grade_level", "status"],
        unique=False,
    )

    # =====================================================
    # BLUEPRINT OBJECTIVES
    # =====================================================

    op.create_table(
        "assessment_blueprint_objectives",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "blueprint_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "learning_objective_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "question_count",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "max_score",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column(
            "order_no",
            sa.SmallInteger(),
            nullable=False,
        ),

        sa.CheckConstraint(
            "max_score > 0",
            name="ck_blueprint_objective_max_score_positive",
        ),
        sa.CheckConstraint(
            "order_no > 0",
            name="ck_blueprint_objective_order_positive",
        ),
        sa.CheckConstraint(
            "question_count > 0",
            name="ck_blueprint_objective_question_count_positive",
        ),

        sa.ForeignKeyConstraint(
            ["blueprint_id"],
            ["assessment_blueprints.id"],
            name="fk_blueprint_objective_blueprint",
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["learning_objective_id"],
            ["learning_objectives.id"],
            name="fk_blueprint_objective_learning_objective",
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "blueprint_id",
            "learning_objective_id",
            name="uq_blueprint_objective_learning",
        ),

        sa.UniqueConstraint(
            "blueprint_id",
            "order_no",
            name="uq_blueprint_objective_order",
        ),
    )

    op.create_index(
        "ix_blueprint_objectives_learning_objective",
        "assessment_blueprint_objectives",
        ["learning_objective_id"],
        unique=False,
    )

    # =====================================================
    # BLUEPRINT QUESTION TYPES
    # =====================================================

    op.create_table(
        "assessment_blueprint_question_types",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "blueprint_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "question_type",
            postgresql.ENUM(
                "single_choice",
                "multiple_choice",
                "true_false",
                "short_text",
                "number",
                "matching",
                "ordering",
                "fill_gaps",
                "formula",
                "image_choice",
                "manual_review",
                name="assessment_question_type",
                create_type=False,
            ),
            nullable=False,
        ),

        sa.Column(
            "question_count",
            sa.SmallInteger(),
            nullable=False,
        ),
        sa.Column(
            "max_score",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
        ),
        sa.Column(
            "order_no",
            sa.SmallInteger(),
            nullable=False,
        ),

        sa.CheckConstraint(
            "max_score > 0",
            name="ck_blueprint_question_type_score_positive",
        ),
        sa.CheckConstraint(
            "order_no > 0",
            name="ck_blueprint_question_type_order_positive",
        ),
        sa.CheckConstraint(
            "question_count > 0",
            name="ck_blueprint_question_type_count_positive",
        ),

        sa.ForeignKeyConstraint(
            ["blueprint_id"],
            ["assessment_blueprints.id"],
            name="fk_blueprint_question_type_blueprint",
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "blueprint_id",
            "order_no",
            name="uq_blueprint_question_type_order",
        ),

        sa.UniqueConstraint(
            "blueprint_id",
            "question_type",
            name="uq_blueprint_question_type",
        ),
    )

    # =====================================================
    # ASSESSMENT -> BLUEPRINT
    # =====================================================

    op.add_column(
        "assessments",
        sa.Column(
            "blueprint_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_assessments_blueprint_id",
        "assessments",
        ["blueprint_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_assessments_blueprint",
        "assessments",
        "assessment_blueprints",
        ["blueprint_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    bind = op.get_bind()

    # =====================================================
    # ASSESSMENT -> BLUEPRINT
    # =====================================================

    op.drop_constraint(
        "fk_assessments_blueprint",
        "assessments",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_assessments_blueprint_id",
        table_name="assessments",
    )

    op.drop_column(
        "assessments",
        "blueprint_id",
    )

    # =====================================================
    # BLUEPRINT CHILD TABLES
    # =====================================================

    op.drop_table(
        "assessment_blueprint_question_types",
    )

    op.drop_index(
        "ix_blueprint_objectives_learning_objective",
        table_name="assessment_blueprint_objectives",
    )

    op.drop_table(
        "assessment_blueprint_objectives",
    )

    # =====================================================
    # BLUEPRINT
    # =====================================================

    op.drop_index(
        "ix_assessment_blueprints_subject_grade_status",
        table_name="assessment_blueprints",
    )

    op.drop_index(
        "ix_assessment_blueprints_creator",
        table_name="assessment_blueprints",
    )

    op.drop_table(
        "assessment_blueprints",
    )

    # =====================================================
    # ENUM TYPES
    # =====================================================

    assessment_blueprint_status_enum.drop(
        bind,
        checkfirst=True,
    )

    assessment_language_enum.drop(
        bind,
        checkfirst=True,
    )
