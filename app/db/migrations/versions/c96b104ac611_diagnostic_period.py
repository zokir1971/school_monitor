"""Session calendar. Existing sessions keep explicit unset periods."""
from alembic import op
import sqlalchemy as sa
revision='c96b104ac611'
down_revision='b95b104ac610'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('diagnostic_sessions') as batch:
        batch.add_column(sa.Column('opens_at',sa.DateTime(timezone=True),nullable=True))
        batch.add_column(sa.Column('closes_at',sa.DateTime(timezone=True),nullable=True))
        batch.create_check_constraint('ck_diagnostic_period','(opens_at IS NULL AND closes_at IS NULL) OR (opens_at IS NOT NULL AND closes_at IS NOT NULL AND closes_at > opens_at)')


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM diagnostic_sessions WHERE opens_at IS NOT NULL OR closes_at IS NOT NULL LIMIT 1')).first():
        raise RuntimeError('Session calendars exist; preserve them before downgrade.')
    with op.batch_alter_table('diagnostic_sessions') as batch:
        batch.drop_constraint('ck_diagnostic_period',type_='check')
        batch.drop_column('closes_at');batch.drop_column('opens_at')
