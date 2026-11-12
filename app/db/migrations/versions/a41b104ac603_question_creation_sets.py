"""Question creation sets and AI result IDs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='a41b104ac603'
down_revision='f37a104ac602'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('teacher_ai_question_runs', sa.Column('item_ids', JSONB(), nullable=True))
    op.create_table('qb_manual_creation_sets',
        sa.Column('token',sa.String(32),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),
        sa.Column('context',JSONB(),nullable=False),
        sa.Column('slots',JSONB(),nullable=False),
        sa.Column('item_ids',JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))

    op.create_index('ix_qb_manual_sets_user_created','qb_manual_creation_sets',['user_id','created_at'])

def downgrade():
    op.drop_index('ix_qb_manual_sets_user_created',table_name='qb_manual_creation_sets')
    op.drop_table('qb_manual_creation_sets')
    op.drop_column('teacher_ai_question_runs','item_ids')
