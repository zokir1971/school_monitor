"""Objective LaTeX and separate upper-grade education tracks, preserving IDs.

Revision ID: e65b2d9c740a
Revises: d41e59c28a07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e65b2d9c740a'
down_revision = 'd41e59c28a07'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('learning_objectives', sa.Column('education_track', sa.String(3), nullable=False, server_default=''))
    for language in ('kz', 'ru'):
        op.add_column('learning_objectives', sa.Column('title_segments_'+language, postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
        for field in ('has_formula_', 'formula_reviewed_'):
            op.add_column('learning_objectives', sa.Column(field+language, sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("""
        UPDATE learning_objective_programs SET education_track = CASE
            WHEN education_track IS NULL OR btrim(education_track) = '' THEN NULL
            WHEN lower(btrim(education_track)) IN ('emn','емн','жмб','естественно-математическое','естественно-математическое направление','жаратылыстану-математикалық','жаратылыстану-математикалық бағыт') THEN 'emn'
            WHEN lower(btrim(education_track)) IN ('ogn','огн','қгб','общественно-гуманитарное','общественно-гуманитарное направление','қоғамдық-гуманитарлық','қоғамдық-гуманитарлық бағыт') THEN 'ogn'
            ELSE education_track END
    """)
    # Unknown old tracks require explicit reconciliation; never guess the direction.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM learning_objective_programs
                   WHERE education_track IS NOT NULL AND
                     (education_track NOT IN ('emn','ogn') OR grade_from < 10 OR grade_to > 11)) THEN
            RAISE EXCEPTION 'Unknown or out-of-range existing programme track. Reconcile education_track before migration.';
        END IF;
    END $$""")
    op.execute("""UPDATE learning_objectives lo SET education_track = p.education_track
        FROM learning_objective_programs p
        WHERE lo.program_id=p.id AND lo.grade_level IN (10,11) AND p.education_track IS NOT NULL""")
    for language in ('kz', 'ru'):
        op.execute(f"""UPDATE learning_objectives SET title_segments_{language} =
            CASE WHEN nullif(btrim(title_{language}), '') IS NULL THEN '[]'::jsonb
            ELSE jsonb_build_array(jsonb_build_object('type','text','text',title_{language})) END""")
    op.drop_constraint('uq_learning_objective_subject_grade_code','learning_objectives',type_='unique')
    op.create_unique_constraint('uq_lo_subject_grade_code_track','learning_objectives',['subject_id','grade_level','code','education_track'])
    op.create_check_constraint('ck_lo_education_track','learning_objectives',"education_track IN ('','emn','ogn') AND (education_track = '' OR grade_level IN (10,11))")
    op.create_check_constraint('ck_lo_program_track','learning_objective_programs',"education_track IS NULL OR (education_track IN ('emn','ogn') AND grade_from >= 10 AND grade_to <= 11)")
    # Align the Python model with the already-supported language norm skill.
    op.drop_constraint('ck_lo_language_skill','learning_objectives',type_='check')
    op.create_check_constraint('ck_lo_language_skill','learning_objectives',"language_skill IS NULL OR language_skill IN ('listening','speaking','reading','writing','listening_speaking','language_norms')")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM learning_objectives
             WHERE education_track <> '' OR has_formula_kz OR has_formula_ru
                OR title_segments_kz @> '[{"type":"latex"}]'::jsonb
                OR title_segments_ru @> '[{"type":"latex"}]'::jsonb) THEN
            RAISE EXCEPTION 'Downgrade would lose tracks or formulas; export/reconcile them first.';
        END IF;
    END $$""")
    op.drop_constraint('ck_lo_program_track','learning_objective_programs',type_='check')
    op.drop_constraint('ck_lo_education_track','learning_objectives',type_='check')
    op.drop_constraint('uq_lo_subject_grade_code_track','learning_objectives',type_='unique')
    op.create_unique_constraint('uq_learning_objective_subject_grade_code','learning_objectives',['subject_id','grade_level','code'])
    for language in ('kz','ru'):
        for field in ('formula_reviewed_', 'has_formula_', 'title_segments_'):
            op.drop_column('learning_objectives',field+language)
    op.drop_column('learning_objectives','education_track')
