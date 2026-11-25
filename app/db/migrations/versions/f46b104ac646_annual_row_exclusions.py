"""Retain school annual rows while excluding them from planning and exports."""
from alembic import op
import sqlalchemy as sa

revision = 'f46b104ac646'
down_revision = 'f45b104ac645'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('school_plan_rows_4', 'school_plan_rows_11'):
        op.add_column(table, sa.Column('is_excluded', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    # Older code would silently re-include excluded tasks after dropping the flag.
    for table in ('school_plan_rows_4', 'school_plan_rows_11'):
        if op.get_bind().execute(sa.text(f'SELECT 1 FROM {table} WHERE is_excluded = true LIMIT 1')).first():
            raise RuntimeError('Сначала восстановите исключённые строки годовых планов / Алдымен алып тасталған жолдарды қалпына келтіріңіз')
    for table in ('school_plan_rows_11', 'school_plan_rows_4'):
        op.drop_column(table, 'is_excluded')
