"""Restore pupil question position and review flags across logins."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='b95b104ac610'
down_revision='a94b104ac609'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('diagnostic_attempts',sa.Column('navigation',postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'")))


def downgrade():
    import json
    rows=op.get_bind().execute(sa.text('SELECT navigation FROM diagnostic_attempts'))
    if any((json.loads(r[0]) if isinstance(r[0],str) else r[0]) != {} for r in rows):
        raise RuntimeError('Navigation contains pupil data; preserve it before downgrade.')
    op.drop_column('diagnostic_attempts','navigation')
