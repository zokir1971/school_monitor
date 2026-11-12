"""Persist algorithm inputs on existing task execution data."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'f38b104ac638'
down_revision = 'f20b104ac620'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('task_execution_data', sa.Column('algorithm_parameters', postgresql.JSONB(), nullable=True))

def downgrade():
    op.drop_column('task_execution_data', 'algorithm_parameters')
