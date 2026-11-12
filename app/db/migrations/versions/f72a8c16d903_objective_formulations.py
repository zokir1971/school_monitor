"""Preserve quarter-specific wording without changing objective IDs.

Revision ID: f72a8c16d903
Revises: e65b2d9c740a
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'f72a8c16d903'
down_revision = 'e65b2d9c740a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'learning_objective_formulations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('learning_objective_id', sa.Integer(), sa.ForeignKey('learning_objectives.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('language', sa.String(2), nullable=False),
        sa.Column('content_key', sa.String(64), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('segments', postgresql.JSONB(), nullable=False),
        sa.Column('quarters', postgresql.JSONB(), nullable=False),
        sa.Column('source_cells', postgresql.JSONB(), nullable=False),
        sa.Column('source_text', sa.Text(), nullable=False),
        sa.Column('metadata_json', postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint('learning_objective_id', 'language', 'content_key', name='uq_lo_formulation_content'),
        sa.CheckConstraint("language IN ('kz','ru')", name='ck_lo_formulation_language'),
    )
    op.create_index('ix_lo_formulation_objective_language', 'learning_objective_formulations', ['learning_objective_id',
                                                                                                'language'])
    # No fabricated backfill: discarded source wording/quarter associations
    # cannot be recovered from a single legacy title. Reimport the source.


def downgrade():
    op.drop_index('ix_lo_formulation_objective_language', table_name='learning_objective_formulations')
    op.drop_table('learning_objective_formulations')
