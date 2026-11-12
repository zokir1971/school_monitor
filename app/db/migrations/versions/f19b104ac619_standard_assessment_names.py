"""Naming parameters on existing reusable work plans; historical titles unchanged."""
from alembic import op
import sqlalchemy as sa
revision='f19b104ac619'
down_revision='e13b104ac613'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('assessment_work_plans',sa.Column('academic_year_start',sa.Integer(),nullable=True))
    op.add_column('assessment_work_plans',sa.Column('section_number',sa.Integer(),nullable=True))
    op.add_column('assessment_work_plans',sa.Column('description',sa.Text(),nullable=True))
    op.create_check_constraint('ck_work_plan_name_year','assessment_work_plans','academic_year_start IS NULL OR academic_year_start BETWEEN 2000 AND 2100')
    op.create_check_constraint('ck_work_plan_sor_number','assessment_work_plans',"section_number IS NULL OR (work_type='sor' AND section_number BETWEEN 1 AND 99)")

def downgrade():
    op.drop_constraint('ck_work_plan_sor_number','assessment_work_plans',type_='check')
    op.drop_constraint('ck_work_plan_name_year','assessment_work_plans',type_='check')
    for column in ('description','section_number','academic_year_start'):op.drop_column('assessment_work_plans',column)
