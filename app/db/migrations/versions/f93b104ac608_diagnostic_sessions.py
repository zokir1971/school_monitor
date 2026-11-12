from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='f93b104ac608'
down_revision='e87b104ac607'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('diagnostic_sessions',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('title_ru',sa.String(length=255),nullable=False),
        sa.Column('title_kk',sa.String(length=255),nullable=False),
        sa.Column('scope_kind',sa.String(length=12),nullable=False),
        sa.Column('scope_id',sa.Integer(),nullable=False),
        sa.Column('participant_grade',sa.Integer(),nullable=False),
        sa.Column('academic_year_start',sa.Integer(),nullable=False),
        sa.Column('status',sa.String(length=12),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('prepared','closed')",name='ck_diagnostic_status'),
        sa.CheckConstraint("scope_kind IN ('school','district','region') AND scope_id>0 AND participant_grade BETWEEN 1 AND 11 AND academic_year_start BETWEEN 2000 AND 2100",name='ck_diagnostic_scope_grade'),
    )
    op.create_index('ix_diagnostic_owner','diagnostic_sessions',['owner_id', 'id'],unique=False)
    op.create_table('diagnostic_subjects',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('session_id',sa.Integer(),sa.ForeignKey('diagnostic_sessions.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('source_plan_id',sa.Integer(),sa.ForeignKey('assessment_work_plans.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('subject_id',sa.Integer(),sa.ForeignKey('subjects.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('order_no',sa.Integer(),nullable=False),
        sa.Column('minutes',sa.Integer(),nullable=False),
        sa.Column('name_ru',sa.String(length=255),nullable=False),
        sa.Column('name_kk',sa.String(length=255),nullable=False),
        sa.Column('snapshots',postgresql.JSONB(),nullable=False),
        sa.CheckConstraint('minutes BETWEEN 1 AND 240',name='ck_diagnostic_minutes'),
        sa.UniqueConstraint('session_id','subject_id',name='uq_diagnostic_subject'),
    )
    op.create_index('ix_diagnostic_subjects_session_id','diagnostic_subjects',['session_id'],unique=False)
    op.create_table('diagnostic_participants',
        sa.Column('id',sa.Integer(),primary_key=True,nullable=False),
        sa.Column('session_id',sa.Integer(),sa.ForeignKey('diagnostic_sessions.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('student_id',sa.Integer(),sa.ForeignKey('school_students.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('school_class_id',sa.Integer(),sa.ForeignKey('school_classes.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('full_name',sa.String(length=455),nullable=False),
        sa.Column('class_label',sa.String(length=32),nullable=False),
        sa.Column('school_name',sa.String(length=255),nullable=False),
        sa.Column('access_hash',sa.String(length=64),nullable=False),
        sa.Column('assignments',postgresql.JSONB(),nullable=False),
        sa.UniqueConstraint('access_hash',name=None),
        sa.UniqueConstraint('session_id','student_id',name='uq_diagnostic_student'),
    )
    op.create_index('ix_diagnostic_participants_session_id','diagnostic_participants',['session_id'],unique=False)

def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM diagnostic_sessions")):
        raise RuntimeError("Sessions exist; downgrade would destroy access/roster data. Nothing deleted.")
    op.drop_table('diagnostic_participants')
    op.drop_table('diagnostic_subjects')
    op.drop_table('diagnostic_sessions')
