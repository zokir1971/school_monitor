"""Persist pupil attempts without creating application users."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'a94b104ac609'
down_revision = 'f93b104ac608'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('diagnostic_attempts',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('participant_id', sa.Integer(), sa.ForeignKey('diagnostic_participants.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('diagnostic_subject_id', sa.Integer(), sa.ForeignKey('diagnostic_subjects.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True)),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('presentation', postgresql.JSONB(), nullable=False),
        sa.Column('private_data', postgresql.JSONB(), nullable=False),
        sa.Column('responses', postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint('participant_id','diagnostic_subject_id',name='uq_diagnostic_attempt'),
        sa.CheckConstraint("status IN ('active','submitted','expired')",name='ck_diagnostic_attempt_status'),
        sa.CheckConstraint('version >= 0 AND deadline_at > started_at',name='ck_diagnostic_attempt_time'))
    op.create_index('ix_diagnostic_attempts_participant_id','diagnostic_attempts',['participant_id'])
    op.create_index('ix_diagnostic_attempt_deadline','diagnostic_attempts',['status','deadline_at'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM diagnostic_attempts LIMIT 1')).first():
        raise RuntimeError('Attempts exist; export and preserve pupil responses before downgrade.')
    op.drop_index('ix_diagnostic_attempt_deadline',table_name='diagnostic_attempts')
    op.drop_index('ix_diagnostic_attempts_participant_id',table_name='diagnostic_attempts')
    op.drop_table('diagnostic_attempts')
