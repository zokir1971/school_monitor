"""Explicit common tasks across variants; existing cards remain non-shared."""
from alembic import op
import sqlalchemy as sa
revision='d85b104ac606'
down_revision='c82b104ac605'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('assessment_work_plan_items',sa.Column('is_shared',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.drop_constraint('uq_work_plan_item_source','assessment_work_plan_items',type_='unique')
    op.create_unique_constraint('uq_work_plan_variant_source','assessment_work_plan_items',['work_plan_id','variant_no','bank_item_id'])

def downgrade():
    duplicate=op.get_bind().execute(sa.text("SELECT 1 FROM assessment_work_plan_items GROUP BY work_plan_id,bank_item_id HAVING count(*)>1 LIMIT 1")).first()
    if duplicate:
        raise RuntimeError('Remove repeated common cards from work variants before downgrade; no data has been deleted.')
    op.drop_constraint('uq_work_plan_variant_source','assessment_work_plan_items',type_='unique')
    op.create_unique_constraint('uq_work_plan_item_source','assessment_work_plan_items',['work_plan_id','bank_item_id'])
    op.drop_column('assessment_work_plan_items','is_shared')
