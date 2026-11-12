"""Add reference metadata without changing legacy quarter consumers.
Revision ID: b83e24d719a6
Revises: 7a61c3e920b4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'b83e24d719a6'
down_revision = '7a61c3e920b4'
branch_labels = None
depends_on = None

TEXT_FIELDS = ('section_code', 'subsection_code', 'section_title_kz', 'section_title_ru', 'subsection_title_kz',
               'subsection_title_ru')
SKILL_CHECK = "language_skill IS NULL OR language_skill IN ('listening','speaking','reading','writing'," \
              "'listening_speaking')"


def upgrade():
    op.create_table('learning_objective_sources',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('document_key', sa.String(150), nullable=False),
                    sa.Column('order_number', sa.String(100), nullable=False),
                    sa.Column('order_date', sa.Date(), nullable=False),
                    sa.Column('edition_date', sa.Date(), nullable=False),
                    sa.Column('title_kz', sa.Text(), nullable=False),
                    sa.Column('title_ru', sa.Text()),
                    sa.Column('file_key_kz', sa.Text()), sa.Column('file_key_ru', sa.Text()),
                    sa.Column('sha256_kz', sa.String(64)), sa.Column('sha256_ru', sa.String(64)),
                    sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.UniqueConstraint('document_key', name='uq_lo_sources_document_key'),
                    )
    op.create_table('learning_objective_programs',
                    sa.Column('id', sa.Integer(), primary_key=True),
                    sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id', ondelete='RESTRICT'),
                              nullable=False),
                    sa.Column('source_id', sa.Integer(),
                              sa.ForeignKey('learning_objective_sources.id', ondelete='RESTRICT'), nullable=False),
                    sa.Column('appendix_number', sa.String(100), nullable=False),
                    sa.Column('variant_key', sa.String(150), nullable=False),
                    sa.Column('title_kz', sa.Text(), nullable=False), sa.Column('title_ru', sa.Text()),
                    sa.Column('grade_from', sa.Integer(), nullable=False),
                    sa.Column('grade_to', sa.Integer(), nullable=False),
                    sa.Column('education_track', sa.String(100)), sa.Column('instruction_language', sa.String(32)),
                    sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.UniqueConstraint('subject_id', 'source_id', 'appendix_number', 'variant_key',
                                        name='uq_lo_programs_variant'),
                    sa.UniqueConstraint('id', 'subject_id', name='uq_lo_programs_id_subject'),
                    sa.CheckConstraint('grade_from BETWEEN 1 AND 12 AND grade_to BETWEEN grade_from AND 12',
                                       name='ck_lo_programs_grades'),
                    )
    op.create_index('ix_lo_programs_subject_active', 'learning_objective_programs', ['subject_id', 'is_active'])
    op.add_column('learning_objectives', sa.Column('program_id', sa.Integer(), nullable=True))
    for name in TEXT_FIELDS:
        op.add_column('learning_objectives',
                      sa.Column(name, sa.String(50) if name.endswith('_code') else sa.Text(), nullable=True))
    op.add_column('learning_objectives', sa.Column('language_skill', sa.String(32), nullable=True))
    for name in ('source_pages_kz', 'source_pages_ru'):
        op.add_column('learning_objectives',
                      sa.Column(name, JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_foreign_key('fk_lo_program_subject', 'learning_objectives', 'learning_objective_programs',
                          ['program_id', 'subject_id'], ['id', 'subject_id'], ondelete='RESTRICT')
    op.create_check_constraint('ck_lo_language_skill', 'learning_objectives', SKILL_CHECK)
    op.create_index('ix_lo_program_grade_skill', 'learning_objectives', ['program_id', 'grade_level', 'language_skill'])
    op.create_table('learning_objective_quarters',
                    sa.Column('learning_objective_id', sa.Integer(),
                              sa.ForeignKey('learning_objectives.id', ondelete='CASCADE'), primary_key=True),
                    sa.Column('quarter', sa.Integer(), primary_key=True),
                    sa.CheckConstraint('quarter BETWEEN 1 AND 4', name='ck_lo_quarters_quarter'),
                    )
    op.create_index('ix_lo_quarters_quarter_objective', 'learning_objective_quarters',
                    ['quarter', 'learning_objective_id'])
    # All original IDs, quarter values and foreign keys remain untouched.
    op.execute(
        'INSERT INTO learning_objective_quarters (learning_objective_id, quarter) SELECT id, quarter FROM '
        'learning_objectives')
    # Phase-1 writes still use the legacy field. Keep its allocation in sync.
    # Remove this transitional trigger in the migration switching all consumers.
    op.execute('''CREATE FUNCTION sync_learning_objective_legacy_quarter() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
      IF TG_OP = 'UPDATE' THEN
        IF OLD.quarter IS DISTINCT FROM NEW.quarter THEN
          DELETE FROM learning_objective_quarters WHERE learning_objective_id = NEW.id AND quarter = OLD.quarter;
        END IF;
      END IF;
      INSERT INTO learning_objective_quarters(learning_objective_id, quarter)
        VALUES(NEW.id, NEW.quarter) ON CONFLICT DO NOTHING;
      RETURN NEW;
    END $$''')
    op.execute('''CREATE TRIGGER trg_learning_objective_legacy_quarter
      AFTER INSERT OR UPDATE OF quarter ON learning_objectives
      FOR EACH ROW EXECUTE FUNCTION sync_learning_objective_legacy_quarter()''')


def downgrade():
    # Do not silently discard reference data once somebody starts filling it.
    op.execute('''DO $$ BEGIN IF EXISTS (SELECT 1 FROM learning_objective_sources) OR EXISTS (SELECT 1 FROM 
    learning_objective_programs) OR EXISTS (SELECT 1 FROM learning_objectives WHERE program_id IS NOT NULL OR 
    language_skill IS NOT NULL OR section_code IS NOT NULL OR subsection_code IS NOT NULL OR section_title_kz IS NOT 
    NULL OR section_title_ru IS NOT NULL OR subsection_title_kz IS NOT NULL OR subsection_title_ru IS NOT NULL OR 
    source_pages_kz <> '[]'::jsonb OR source_pages_ru <> '[]'::jsonb) OR EXISTS (SELECT 1 FROM 
    learning_objective_quarters q JOIN learning_objectives o ON o.id=q.learning_objective_id WHERE 
    q.quarter<>o.quarter) THEN RAISE EXCEPTION 'Reference data exists; downgrade would lose it. Export and review it 
    before rollback.'; END IF; END $$''')
    op.execute('DROP TRIGGER trg_learning_objective_legacy_quarter ON learning_objectives')
    op.execute('DROP FUNCTION sync_learning_objective_legacy_quarter()')
    op.drop_index('ix_lo_quarters_quarter_objective', table_name='learning_objective_quarters')
    op.drop_table('learning_objective_quarters')
    op.drop_index('ix_lo_program_grade_skill', table_name='learning_objectives')
    op.drop_constraint('ck_lo_language_skill', 'learning_objectives', type_='check')
    op.drop_constraint('fk_lo_program_subject', 'learning_objectives', type_='foreignkey')
    for name in ('source_pages_ru', 'source_pages_kz', 'language_skill', *reversed(TEXT_FIELDS), 'program_id'):
        op.drop_column('learning_objectives', name)
    op.drop_index('ix_lo_programs_subject_active', table_name='learning_objective_programs')
    op.drop_table('learning_objective_programs')
    op.drop_table('learning_objective_sources')
