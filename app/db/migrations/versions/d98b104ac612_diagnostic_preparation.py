"""Persistent, resumable diagnostic preparation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='d98b104ac612'
down_revision='c96b104ac611'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('diagnostic_preparations',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('session_id',sa.Integer(),sa.ForeignKey('diagnostic_sessions.id',ondelete='RESTRICT'),nullable=False,unique=True),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('request_key',sa.String(32),nullable=False),sa.Column('state',sa.String(12),nullable=False),
        sa.Column('spec',postgresql.JSONB(),nullable=False),sa.Column('nonce',sa.String(32),nullable=False),sa.Column('key_tag',sa.String(64),nullable=False),
        sa.Column('cursor',sa.Integer(),nullable=False),sa.Column('pupil_count',sa.Integer(),nullable=False),sa.Column('error',sa.String(1000)),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint('owner_id','request_key',name='uq_diagnostic_preparation_request'),
        sa.CheckConstraint("state IN ('queued','running','failed','completed','cancelled')",name='ck_diagnostic_preparation_state'),
        sa.CheckConstraint('cursor >= 0 AND pupil_count BETWEEN 0 AND 100000',name='ck_diagnostic_preparation_counts'))
    op.create_index('ix_diagnostic_preparation_queue','diagnostic_preparations',['state','id'])


def downgrade():
    if op.get_bind().execute(sa.text('SELECT 1 FROM diagnostic_preparations LIMIT 1')).first():
        raise RuntimeError('Preparation jobs exist. Preserve sessions and credentials before downgrade.')
    op.drop_index('ix_diagnostic_preparation_queue',table_name='diagnostic_preparations')
    op.drop_table('diagnostic_preparations')
