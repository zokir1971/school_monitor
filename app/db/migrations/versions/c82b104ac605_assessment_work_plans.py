"""Reusable multilingual work plans; execution remains school-bound."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'c82b104ac605'
down_revision = 'b48b104ac604'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('assessment_work_plans',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('scope_kind', sa.String(length=12), nullable=False),
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('district_id', sa.Integer(), sa.ForeignKey('districts.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('region_id', sa.Integer(), sa.ForeignKey('regions.id', ondelete='RESTRICT'), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('subject_id', sa.Integer(), sa.ForeignKey('subjects.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('curriculum_subject_id', sa.Integer(), sa.ForeignKey('subjects.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('participant_grade', sa.Integer(), nullable=False),
        sa.Column('curriculum_grade', sa.Integer(), nullable=False),
        sa.Column('work_type', sa.String(length=12), nullable=False),
        sa.Column('input_mode', sa.String(length=12), nullable=False),
        sa.Column('quarter', sa.Integer(), nullable=True),
        sa.Column('education_track', sa.String(length=12), nullable=True),
        sa.Column('variant_count', sa.Integer(), nullable=False),
        sa.Column('language_policy', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='draft'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.CheckConstraint("(work_type = 'baseline' AND participant_grade > 1 AND curriculum_grade = participant_grade-1 AND quarter IS NULL) OR (work_type IN ('sor','soch') AND curriculum_grade = participant_grade AND quarter IS NOT NULL AND quarter BETWEEN 1 AND 4 AND subject_id = curriculum_subject_id)", name='ck_work_plan_curriculum'),
        sa.CheckConstraint('participant_grade BETWEEN 1 AND 11 AND curriculum_grade BETWEEN 1 AND 11', name='ck_work_plan_grades'),
        sa.CheckConstraint("input_mode IN ('manual','online')", name='ck_work_plan_input'),
        sa.CheckConstraint("language_policy IN ('auto','kk','ru','both')", name='ck_work_plan_language'),
        sa.CheckConstraint("(scope_kind='school' AND school_id IS NOT NULL AND district_id IS NULL AND region_id IS NULL) OR (scope_kind='district' AND district_id IS NOT NULL AND school_id IS NULL AND region_id IS NULL) OR (scope_kind='region' AND region_id IS NOT NULL AND school_id IS NULL AND district_id IS NULL)", name='ck_work_plan_scope'),
        sa.CheckConstraint("status IN ('draft','prepared')", name='ck_work_plan_status'),
        sa.CheckConstraint("education_track IN ('general','emn','ogn') OR education_track IS NULL", name='ck_work_plan_track'),
        sa.CheckConstraint('(curriculum_grade IN (10,11) AND education_track IS NOT NULL) OR (curriculum_grade < 10 AND education_track IS NULL)', name='ck_work_plan_track_grade'),
        sa.CheckConstraint("work_type IN ('baseline','sor','soch')", name='ck_work_plan_type'),
        sa.CheckConstraint('variant_count BETWEEN 2 AND 10', name='ck_work_plan_variants'),
    )
    op.create_index('ix_work_plan_owner_id', 'assessment_work_plans', ['created_by_user_id', 'id'])
    op.create_table('assessment_work_plan_items',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('work_plan_id', sa.Integer(), sa.ForeignKey('assessment_work_plans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('bank_item_id', sa.Integer(), sa.ForeignKey('question_bank_items.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('variant_no', sa.Integer(), nullable=False),
        sa.Column('order_no', sa.Integer(), nullable=False),
        sa.Column('question_type', sa.String(length=32), nullable=False),
        sa.Column('difficulty', sa.String(length=16), nullable=False),
        sa.Column('max_score', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('source_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('objectives', postgresql.JSONB(), nullable=False),
        sa.Column('payloads', postgresql.JSONB(), nullable=False),
        sa.CheckConstraint('variant_no BETWEEN 1 AND 10 AND order_no > 0 AND max_score > 0', name='ck_work_plan_item_values'),
        sa.UniqueConstraint('work_plan_id', 'variant_no', 'order_no', name='uq_work_plan_item_order'),
        sa.UniqueConstraint('work_plan_id', 'bank_item_id', name='uq_work_plan_item_source'),
    )

def downgrade():
    op.drop_table('assessment_work_plan_items')
    op.drop_table('assessment_work_plans')
