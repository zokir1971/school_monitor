"""Versioned in-system delivery of monthly plan notifications."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'f39b104ac639'
down_revision = 'f38b104ac638'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('school_month_plan_internal_notices',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('notification_id', sa.Integer(), sa.ForeignKey('school_month_plan_notifications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recipient_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('digest', sa.String(64), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('sent_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('notification_id', 'revision', name='uq_month_internal_notice_revision'))
    op.create_index('ix_month_internal_notice_recipient', 'school_month_plan_internal_notices', ['recipient_user_id','notification_id','id'])

def downgrade():
    op.drop_table('school_month_plan_internal_notices')
