"""Bilingual titles and immutable participant assignments.
Revision ID: e87b104ac607
Revises: d85b104ac606
"""
from alembic import op
import sqlalchemy as sa
revision='e87b104ac607'
down_revision='d85b104ac606'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('assessment_work_plans',sa.Column('title_kk',sa.String(255),nullable=True))
    op.add_column('assessment_work_plans',sa.Column('title_ru',sa.String(255),nullable=True))
    # Existing titles have no trustworthy language metadata. Preserve without guessing.
    op.create_table('assessment_work_assignments',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('work_plan_id',sa.Integer(),sa.ForeignKey('assessment_work_plans.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('created_by_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('academic_year_start',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint('academic_year_start BETWEEN 2000 AND 2100',name='ck_work_assignment_year'))
    op.create_index('ix_work_assignment_plan','assessment_work_assignments',['work_plan_id','id'])
    op.create_table('assessment_work_participants',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('assignment_id',sa.Integer(),sa.ForeignKey('assessment_work_assignments.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('work_plan_id',sa.Integer(),sa.ForeignKey('assessment_work_plans.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('student_id',sa.Integer(),sa.ForeignKey('school_students.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('school_id',sa.Integer(),sa.ForeignKey('schools.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('school_class_id',sa.Integer(),sa.ForeignKey('school_classes.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('full_name',sa.String(455),nullable=False),sa.Column('school_name',sa.String(255),nullable=False),
        sa.Column('class_label',sa.String(32),nullable=False),sa.Column('language',sa.String(2),nullable=False),
        sa.Column('variant_no',sa.Integer(),nullable=False),
        sa.UniqueConstraint('work_plan_id','student_id',name='uq_work_plan_student'),
        sa.CheckConstraint("language IN ('kk','ru') AND variant_no BETWEEN 1 AND 10",name='ck_work_participant_values'))
    op.create_index('ix_work_participant_plan_id','assessment_work_participants',['work_plan_id','id'])
    op.create_index('ix_work_participant_class_variant','assessment_work_participants',['work_plan_id','school_class_id','variant_no'])
    op.create_index('ix_work_participant_assignment','assessment_work_participants',['assignment_id','id'])

def downgrade():
    bind=op.get_bind()
    if bind.scalar(sa.text('SELECT count(*) FROM assessment_work_assignments')):
        raise RuntimeError('Assignments exist. Downgrade would destroy participant data; back up and resolve explicitly.')
    op.drop_table('assessment_work_participants');op.drop_table('assessment_work_assignments')
    op.drop_column('assessment_work_plans','title_ru');op.drop_column('assessment_work_plans','title_kk')
