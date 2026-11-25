"""Remember draft inclusion flags while a school annual row is excluded."""
from alembic import op
import sqlalchemy as sa

revision = 'f47b104ac647'
down_revision = 'f46b104ac646'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('school_month_plan_items', sa.Column('annual_exclusion_was_included', sa.Boolean(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM school_month_plan_items WHERE annual_exclusion_was_included IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Сначала восстановите годовые строки с исключёнными месячными черновиками / Алдымен айлық нобайлары алынып тасталған жылдық жолдарды қалпына келтіріңіз')
    op.drop_column('school_month_plan_items', 'annual_exclusion_was_included')
