"""Persist editable PDF import previews.
Revision ID: c92f86a10d35
Revises: b83e24d719a6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'c92f86a10d35'
down_revision = 'b83e24d719a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('learning_objective_import_drafts',
                    sa.Column('id', sa.String(36), primary_key=True),
                    sa.Column('owner_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='RESTRICT'),
                              nullable=False),
                    sa.Column('payload', JSONB(), nullable=False),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
                    sa.Column('confirmed_at', sa.DateTime(timezone=True)),
                    sa.Column('result', JSONB()),
                    )
    op.create_index('ix_lo_import_owner_expires', 'learning_objective_import_drafts', ['owner_user_id', 'expires_at'])


def downgrade():
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM learning_objective_import_drafts) THEN RAISE EXCEPTION 'Import drafts "
        "exist; review their data before downgrade.'; END IF; END $$")
    op.drop_index('ix_lo_import_owner_expires', table_name='learning_objective_import_drafts')
    op.drop_table('learning_objective_import_drafts')
