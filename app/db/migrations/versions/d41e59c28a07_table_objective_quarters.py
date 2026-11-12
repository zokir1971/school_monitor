"""Table provenance, language norms and stable question-bank quarter."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "d41e59c28a07"
down_revision = "c92f86a10d35"
branch_labels = None
depends_on = None
OLD_SKILL = "language_skill IS NULL OR language_skill IN ('listening','speaking','reading','writing','listening_speaking')"
NEW_SKILL = "language_skill IS NULL OR language_skill IN ('listening','speaking','reading','writing','listening_speaking','language_norms')"


def upgrade():
    for language in ("kz", "ru"):
        op.add_column(
            "learning_objectives",
            sa.Column(
                "source_cells_" + language,
                JSONB(),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
        )
    op.drop_constraint("ck_lo_language_skill", "learning_objectives", type_="check")
    op.create_check_constraint("ck_lo_language_skill", "learning_objectives", NEW_SKILL)
    op.add_column(
        "question_bank_items", sa.Column("quarter", sa.Integer(), nullable=True)
    )
    op.create_check_constraint(
        "ck_qb_item_quarter",
        "question_bank_items",
        "quarter IS NULL OR quarter BETWEEN 1 AND 4",
    )
    op.execute("""UPDATE question_bank_items b SET quarter = s.quarter
      FROM (SELECT l.question_bank_item_id, min(o.quarter) AS quarter
        FROM question_bank_item_objectives l JOIN learning_objectives o ON o.id=l.learning_objective_id
        GROUP BY l.question_bank_item_id HAVING count(DISTINCT o.quarter)=1) s
      WHERE b.id=s.question_bank_item_id""")
    # Changing the legacy field must no longer discard another valid allocation.
    op.execute(
        """CREATE OR REPLACE FUNCTION sync_learning_objective_legacy_quarter() RETURNS trigger
      LANGUAGE plpgsql AS $$ BEGIN
        INSERT INTO learning_objective_quarters(learning_objective_id,quarter)
          VALUES(NEW.id,NEW.quarter) ON CONFLICT DO NOTHING;
        RETURN NEW;
      END $$"""
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM learning_objectives WHERE source_cells_kz<>'[]'::jsonb OR source_cells_ru<>'[]'::jsonb OR language_skill='language_norms')
      OR EXISTS (SELECT 1 FROM learning_objective_quarters q JOIN learning_objectives o ON o.id=q.learning_objective_id WHERE q.quarter<>o.quarter)
      OR EXISTS (SELECT 1 FROM question_bank_items b JOIN question_bank_item_objectives l ON l.question_bank_item_id=b.id JOIN learning_objectives o ON o.id=l.learning_objective_id WHERE b.quarter<>o.quarter)
      THEN RAISE EXCEPTION 'Table import or multi-quarter data exists. Export and review before downgrade.'; END IF;
    END $$""")
    op.drop_constraint("ck_qb_item_quarter", "question_bank_items", type_="check")
    op.drop_column("question_bank_items", "quarter")
    op.drop_constraint("ck_lo_language_skill", "learning_objectives", type_="check")
    op.create_check_constraint("ck_lo_language_skill", "learning_objectives", OLD_SKILL)
    for language in ("kz", "ru"):
        op.drop_column("learning_objectives", "source_cells_" + language)
    op.execute(
        """CREATE OR REPLACE FUNCTION sync_learning_objective_legacy_quarter() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP = 'UPDATE' AND OLD.quarter IS DISTINCT FROM NEW.quarter THEN
        DELETE FROM learning_objective_quarters WHERE learning_objective_id=NEW.id AND quarter=OLD.quarter;
      END IF;
      INSERT INTO learning_objective_quarters(learning_objective_id,quarter) VALUES(NEW.id,NEW.quarter) ON CONFLICT DO NOTHING;
      RETURN NEW;
    END $$"""
    )
