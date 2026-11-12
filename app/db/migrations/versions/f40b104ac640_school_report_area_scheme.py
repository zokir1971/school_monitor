"""One versioned report layout per school."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f40b104ac640'
down_revision = 'f39b104ac639'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('school_report_area_schemes',
        sa.Column('school_id', sa.Integer(), sa.ForeignKey('schools.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('configuration', postgresql.JSONB(), nullable=False),
        sa.Column('updated_by_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade():
    op.drop_table('school_report_area_schemes')
