"""Allow the same objective code in different programs without changing IDs."""
from alembic import op
import sqlalchemy as sa

revision = 'a61c7d2e904b'
down_revision = 'e54f155f52d9'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('uq_lo_subject_grade_code_track', 'learning_objectives', type_='unique')
    op.create_unique_constraint(
        'uq_lo_program_subject_grade_code_track', 'learning_objectives',
        ['program_id', 'subject_id', 'grade_level', 'code', 'education_track'],
    )
    # PostgreSQL UNIQUE allows multiple NULL program IDs. Keep legacy rows unique too.
    op.create_index(
        'uq_lo_legacy_subject_grade_code_track', 'learning_objectives',
        ['subject_id', 'grade_level', 'code', 'education_track'], unique=True,
        postgresql_where=sa.text('program_id IS NULL'),
    )


def downgrade():
    # Check first; never delete or merge objectives to restore the old constraint.
    duplicate = op.get_bind().execute(sa.text('''
        SELECT 1 FROM learning_objectives
        GROUP BY subject_id, grade_level, code, education_track
        HAVING count(*) > 1 LIMIT 1
    ''')).first()
    if duplicate is not None:
        raise RuntimeError(
            'Откат невозможен: одинаковые коды уже используются разными программами. '
            'Данные не изменены. Сначала разрешите конфликты вручную.'
        )
    op.drop_index('uq_lo_legacy_subject_grade_code_track', table_name='learning_objectives')
    op.drop_constraint('uq_lo_program_subject_grade_code_track', 'learning_objectives', type_='unique')
    op.create_unique_constraint(
        'uq_lo_subject_grade_code_track', 'learning_objectives',
        ['subject_id', 'grade_level', 'code', 'education_track'],
    )
