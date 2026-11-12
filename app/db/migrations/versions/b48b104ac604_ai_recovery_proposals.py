"""Retain failed generated candidates separately from valid bank items."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'b48b104ac604'
down_revision = 'a41b104ac603'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('teacher_ai_question_runs', sa.Column('proposal', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('teacher_ai_question_runs', 'proposal')
