"""Durable, deduplicated AI translation proposals; no question data is rewritten."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='f37a104ac602'
down_revision='e26b104ac601'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('qb_translation_requests',
        sa.Column('item_id',sa.Integer(),sa.ForeignKey('question_bank_items.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('source_hash',sa.String(64),primary_key=True),
        sa.Column('language',sa.String(2),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('attempt_token',sa.String(32),nullable=False),
        sa.Column('status',sa.String(12),nullable=False),
        sa.Column('values_json',postgresql.JSONB()),
        sa.Column('error_code',sa.String(32)),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("status IN ('running','proposed','failed')",name='ck_qb_translation_status'),
        sa.CheckConstraint("language IN ('ru','kk')",name='ck_qb_translation_language'))

def downgrade():
    op.drop_table('qb_translation_requests')
