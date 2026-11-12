"""add question bank

Revision ID: 479442dac1ef
Revises: 2110f71e69c6
Create Date: 2026-09-19 17:35:57.568355

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "479442dac1ef"
down_revision: Union[str, None] = "2110f71e69c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# =========================================================
# EXISTING POSTGRESQL ENUMS
# =========================================================
#
# Эти ENUM уже созданы предыдущими миграциями.
# Здесь мы только используем существующие PostgreSQL types.
# create_type=False запрещает повторное CREATE TYPE.
# =========================================================

assessment_question_type_enum = postgresql.ENUM(
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
)


assessment_language_enum = postgresql.ENUM(
    "kk",
    "ru",
    "en",
    name="assessment_language",
    create_type=False,
)


# =========================================================
# NEW POSTGRESQL ENUMS
# =========================================================
#
# Эти ENUM появляются впервые в этой миграции.
# Создаём их явно в upgrade() и удаляем в downgrade().
# =========================================================

assessment_question_difficulty_enum = postgresql.ENUM(
    "basic",
    "medium",
    "advanced",
    name="assessment_question_difficulty",
    create_type=False,
)


question_bank_item_status_enum = postgresql.ENUM(
    "draft",
    "review",
    "ready",
    "rejected",
    "archived",
    name="question_bank_item_status",
    create_type=False,
)


question_bank_item_origin_enum = postgresql.ENUM(
    "manual",
    "ai_generated",
    "imported",
    name="question_bank_item_origin",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # =====================================================
    # CREATE NEW POSTGRESQL ENUM TYPES
    # =====================================================

    assessment_question_difficulty_enum.create(
        bind,
        checkfirst=True,
    )

    question_bank_item_status_enum.create(
        bind,
        checkfirst=True,
    )

    question_bank_item_origin_enum.create(
        bind,
        checkfirst=True,
    )

    # =====================================================
    # QUESTION BANK ITEMS
    # =====================================================

    op.create_table(
        "question_bank_items",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        # -------------------------------------------------
        # EDUCATION SCOPE
        # -------------------------------------------------

        sa.Column(
            "subject_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "grade_level",
            sa.Integer(),
            nullable=False,
        ),

        # -------------------------------------------------
        # CLASSIFICATION
        # -------------------------------------------------

        sa.Column(
            "question_type",
            assessment_question_type_enum,
            nullable=False,
        ),

        sa.Column(
            "difficulty",
            assessment_question_difficulty_enum,
            nullable=False,
        ),

        sa.Column(
            "language",
            assessment_language_enum,
            nullable=False,
        ),

        sa.Column(
            "status",
            question_bank_item_status_enum,
            nullable=False,
        ),

        sa.Column(
            "origin",
            question_bank_item_origin_enum,
            nullable=False,
        ),

        # -------------------------------------------------
        # CONTENT
        # -------------------------------------------------

        sa.Column(
            "title",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "text",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "instruction",
            sa.Text(),
            nullable=True,
        ),

        # -------------------------------------------------
        # QUESTION CONTRACT
        # -------------------------------------------------

        sa.Column(
            "content",
            postgresql.JSONB(
                astext_type=sa.Text(),
            ),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),

        sa.Column(
            "answer_key",
            postgresql.JSONB(
                astext_type=sa.Text(),
            ),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),

        sa.Column(
            "grading_settings",
            postgresql.JSONB(
                astext_type=sa.Text(),
            ),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),

        # -------------------------------------------------
        # SCORING
        # -------------------------------------------------

        sa.Column(
            "max_score",
            sa.Numeric(
                precision=10,
                scale=2,
            ),
            nullable=False,
        ),

        # -------------------------------------------------
        # AUTHOR / EXPERT INFORMATION
        # -------------------------------------------------

        sa.Column(
            "explanation",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "author_comment",
            sa.Text(),
            nullable=True,
        ),

        # -------------------------------------------------
        # AUDIT
        # -------------------------------------------------

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

        # -------------------------------------------------
        # CHECK CONSTRAINTS
        # -------------------------------------------------

        sa.CheckConstraint(
            "grade_level BETWEEN 1 AND 12",
            name="ck_question_bank_items_grade_level",
        ),

        sa.CheckConstraint(
            "max_score > 0",
            name="ck_question_bank_items_max_score_positive",
        ),

        # -------------------------------------------------
        # FOREIGN KEYS
        # -------------------------------------------------

        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            ondelete="RESTRICT",
        ),

        # -------------------------------------------------
        # PRIMARY KEY
        # -------------------------------------------------

        sa.PrimaryKeyConstraint("id"),
    )

    # =====================================================
    # QUESTION BANK ITEM INDEXES
    # =====================================================

    op.create_index(
        op.f("ix_question_bank_items_created_by_user_id"),
        "question_bank_items",
        ["created_by_user_id"],
        unique=False,
    )

    op.create_index(
        op.f("ix_question_bank_items_difficulty"),
        "question_bank_items",
        ["difficulty"],
        unique=False,
    )

    op.create_index(
        op.f("ix_question_bank_items_grade_level"),
        "question_bank_items",
        ["grade_level"],
        unique=False,
    )

    op.create_index(
        op.f("ix_question_bank_items_language"),
        "question_bank_items",
        ["language"],
        unique=False,
    )

    op.create_index(
        "ix_question_bank_items_lookup",
        "question_bank_items",
        [
            "subject_id",
            "grade_level",
            "language",
            "status",
        ],
        unique=False,
    )

    op.create_index(
        op.f("ix_question_bank_items_origin"),
        "question_bank_items",
        ["origin"],
        unique=False,
    )

    op.create_index(
        op.f("ix_question_bank_items_question_type"),
        "question_bank_items",
        ["question_type"],
        unique=False,
    )

    op.create_index(
        op.f("ix_question_bank_items_status"),
        "question_bank_items",
        ["status"],
        unique=False,
    )

    op.create_index(
        op.f("ix_question_bank_items_subject_id"),
        "question_bank_items",
        ["subject_id"],
        unique=False,
    )

    # =====================================================
    # QUESTION BANK ITEM OBJECTIVES
    # =====================================================

    op.create_table(
        "question_bank_item_objectives",

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "question_bank_item_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "learning_objective_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "order_no",
            sa.Integer(),
            nullable=False,
        ),

        # -------------------------------------------------
        # CHECK CONSTRAINTS
        # -------------------------------------------------

        sa.CheckConstraint(
            "order_no > 0",
            name="ck_question_bank_item_objective_order_positive",
        ),

        # -------------------------------------------------
        # FOREIGN KEYS
        # -------------------------------------------------

        sa.ForeignKeyConstraint(
            ["learning_objective_id"],
            ["learning_objectives.id"],
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["question_bank_item_id"],
            ["question_bank_items.id"],
            ondelete="CASCADE",
        ),

        # -------------------------------------------------
        # PRIMARY KEY
        # -------------------------------------------------

        sa.PrimaryKeyConstraint("id"),

        # -------------------------------------------------
        # UNIQUE CONSTRAINTS
        # -------------------------------------------------

        sa.UniqueConstraint(
            "question_bank_item_id",
            "learning_objective_id",
            name="uq_question_bank_item_objective_learning",
        ),

        sa.UniqueConstraint(
            "question_bank_item_id",
            "order_no",
            name="uq_question_bank_item_objective_order",
        ),
    )

    # =====================================================
    # QUESTION BANK OBJECTIVE INDEXES
    # =====================================================

    op.create_index(
        op.f(
            "ix_question_bank_item_objectives_learning_objective_id"
        ),
        "question_bank_item_objectives",
        ["learning_objective_id"],
        unique=False,
    )

    op.create_index(
        op.f(
            "ix_question_bank_item_objectives_question_bank_item_id"
        ),
        "question_bank_item_objectives",
        ["question_bank_item_id"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    # =====================================================
    # QUESTION BANK ITEM OBJECTIVES
    # =====================================================

    op.drop_index(
        op.f(
            "ix_question_bank_item_objectives_question_bank_item_id"
        ),
        table_name="question_bank_item_objectives",
    )

    op.drop_index(
        op.f(
            "ix_question_bank_item_objectives_learning_objective_id"
        ),
        table_name="question_bank_item_objectives",
    )

    op.drop_table(
        "question_bank_item_objectives"
    )

    # =====================================================
    # QUESTION BANK ITEMS
    # =====================================================

    op.drop_index(
        op.f("ix_question_bank_items_subject_id"),
        table_name="question_bank_items",
    )

    op.drop_index(
        op.f("ix_question_bank_items_status"),
        table_name="question_bank_items",
    )

    op.drop_index(
        op.f("ix_question_bank_items_question_type"),
        table_name="question_bank_items",
    )

    op.drop_index(
        op.f("ix_question_bank_items_origin"),
        table_name="question_bank_items",
    )

    op.drop_index(
        "ix_question_bank_items_lookup",
        table_name="question_bank_items",
    )

    op.drop_index(
        op.f("ix_question_bank_items_language"),
        table_name="question_bank_items",
    )

    op.drop_index(
        op.f("ix_question_bank_items_grade_level"),
        table_name="question_bank_items",
    )

    op.drop_index(
        op.f("ix_question_bank_items_difficulty"),
        table_name="question_bank_items",
    )

    op.drop_index(
        op.f("ix_question_bank_items_created_by_user_id"),
        table_name="question_bank_items",
    )

    op.drop_table(
        "question_bank_items"
    )

    # =====================================================
    # DROP ENUM TYPES CREATED BY THIS MIGRATION
    # =====================================================
    #
    # ВАЖНО:
    # assessment_question_type и assessment_language
    # здесь НЕ удаляем — они были созданы ранее и используются
    # другими Assessment-таблицами.
    # =====================================================

    question_bank_item_origin_enum.drop(
        bind,
        checkfirst=True,
    )

    question_bank_item_status_enum.drop(
        bind,
        checkfirst=True,
    )

    assessment_question_difficulty_enum.drop(
        bind,
        checkfirst=True,
    )
    