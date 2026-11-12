"""Shared access recovery branch; independent of untested report changes."""
from alembic import op
import sqlalchemy as sa

revision='f41b104ac641'
down_revision='5ae5aaaa595b'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('access_recovery_grants',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('issued_by_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('token_hash',sa.String(64),nullable=False,unique=True),
        sa.Column('credential_stamp',sa.String(64),nullable=False),
        sa.Column('issuer_stamp',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('used_at',sa.DateTime(timezone=True)),sa.Column('revoked_at',sa.DateTime(timezone=True)))
    op.create_index('ix_access_recovery_user_created','access_recovery_grants',['user_id','created_at'])
    op.create_index('uq_access_recovery_open_user','access_recovery_grants',['user_id'],unique=True,postgresql_where=sa.text('used_at IS NULL AND revoked_at IS NULL'))
    op.create_table('access_recovery_audit',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('actor_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('target_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('action',sa.String(24),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index('ix_access_recovery_audit_target','access_recovery_audit',['target_user_id','created_at'])
    op.create_table('access_recovery_limits',sa.Column('bucket_key',sa.String(64),primary_key=True),
        sa.Column('attempts',sa.Integer(),nullable=False),sa.Column('resets_at',sa.DateTime(timezone=True),nullable=False))


def downgrade():
    op.drop_table('access_recovery_limits')
    op.drop_table('access_recovery_audit')
    op.drop_table('access_recovery_grants')
