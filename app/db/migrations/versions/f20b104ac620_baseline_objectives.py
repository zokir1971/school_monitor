"""Explicit baseline type and generic objective scoring; no new result tables."""
from alembic import op
revision='f20b104ac620'
down_revision='f19b104ac619'
branch_labels=None
depends_on=None

def upgrade():
    op.execute("ALTER TYPE assessment_type ADD VALUE IF NOT EXISTS 'baseline'")
    op.execute("ALTER TYPE assessment_mode ADD VALUE IF NOT EXISTS 'by_objectives'")

def downgrade():
    # PostgreSQL enum values are retained: deleting them would invalidate saved works.
    pass
