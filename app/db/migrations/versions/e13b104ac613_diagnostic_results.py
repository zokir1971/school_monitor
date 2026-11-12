"""Connect diagnostic attempts to the canonical assessment results; no new result tables."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='e13b104ac613'
down_revision='d98b104ac612'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('diagnostic_subjects',sa.Column('assessment_context',JSONB()))
    op.execute("UPDATE diagnostic_subjects d SET assessment_context=jsonb_build_object('work_type',p.work_type,'quarter',p.quarter,'curriculum_grade',p.curriculum_grade,'education_track',p.education_track) FROM assessment_work_plans p WHERE p.id=d.source_plan_id")
    op.add_column('diagnostic_sessions',sa.Column('results_published_at',sa.DateTime(timezone=True)))
    op.add_column('assessments',sa.Column('diagnostic_subject_id',sa.Integer()))
    op.create_foreign_key('fk_assessment_diagnostic_subject','assessments','diagnostic_subjects',['diagnostic_subject_id'],['id'],ondelete='RESTRICT')
    op.add_column('assessments',sa.Column('diagnostic_variant',sa.Integer()))
    op.add_column('assessments',sa.Column('diagnostic_language',sa.String(2)))
    op.create_unique_constraint('uq_assessment_diagnostic_context','assessments',['diagnostic_subject_id','school_id','diagnostic_variant','diagnostic_language'])
    op.create_check_constraint('ck_assessment_diagnostic_context','assessments',"(diagnostic_subject_id IS NULL AND diagnostic_variant IS NULL AND diagnostic_language IS NULL) OR (diagnostic_subject_id IS NOT NULL AND diagnostic_variant IS NOT NULL AND diagnostic_language IS NOT NULL AND diagnostic_variant > 0 AND diagnostic_language IN ('ru','kk'))")
    op.add_column('assessment_questions',sa.Column('diagnostic_snapshot',JSONB()))
    op.add_column('diagnostic_attempts',sa.Column('assessment_student_id',sa.Integer()))
    op.create_foreign_key('fk_diagnostic_attempt_student','diagnostic_attempts','assessment_students',['assessment_student_id'],['id'],ondelete='RESTRICT')
    op.create_unique_constraint('uq_diagnostic_attempt_student','diagnostic_attempts',['assessment_student_id'])
    op.add_column('diagnostic_attempts',sa.Column('grading_error',sa.String(32)))
    op.create_index('ix_diagnostic_result_queue','diagnostic_attempts',['id'],postgresql_where=sa.text("status IN ('submitted','expired') AND assessment_student_id IS NULL AND grading_error IS NULL"))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM diagnostic_attempts WHERE assessment_student_id IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Diagnostic results exist. Preserve their links before downgrading.')
    op.drop_index('ix_diagnostic_result_queue',table_name='diagnostic_attempts')
    op.drop_column('diagnostic_attempts','grading_error')
    op.drop_constraint('uq_diagnostic_attempt_student','diagnostic_attempts',type_='unique')
    op.drop_constraint('fk_diagnostic_attempt_student','diagnostic_attempts',type_='foreignkey')
    op.drop_column('diagnostic_attempts','assessment_student_id')
    op.drop_column('assessment_questions','diagnostic_snapshot')
    op.drop_constraint('ck_assessment_diagnostic_context','assessments',type_='check')
    op.drop_constraint('uq_assessment_diagnostic_context','assessments',type_='unique')
    op.drop_constraint('fk_assessment_diagnostic_subject','assessments',type_='foreignkey')
    for name in ('diagnostic_language','diagnostic_variant','diagnostic_subject_id'):op.drop_column('assessments',name)
    op.drop_column('diagnostic_sessions','results_published_at')
    op.drop_column('diagnostic_subjects','assessment_context')
