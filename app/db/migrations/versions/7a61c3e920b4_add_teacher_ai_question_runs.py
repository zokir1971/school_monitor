"""Durable single-question AI requests.

Revision ID: 7a61c3e920b4
Revises: f4e14abc6f53
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '7a61c3e920b4'
down_revision = 'f4e14abc6f53'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('teacher_ai_question_runs',
                    sa.Column('token', sa.String(32), primary_key=True),
                    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
                    sa.Column('status', sa.String(16), nullable=False, server_default='pending'),
                    sa.Column('fingerprint', sa.String(64), nullable=True),
                    sa.Column('item_id', sa.Integer(), sa.ForeignKey('question_bank_items.id', ondelete='SET NULL'),
                              nullable=True),
                    sa.Column('warnings', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
                    sa.Column('error_code', sa.String(100), nullable=True),
                    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.CheckConstraint("status IN ('pending','running','completed','failed')",
                                       name='ck_teacher_ai_question_runs_status'),
                    )
    op.create_index('ix_teacher_ai_question_runs_user_created', 'teacher_ai_question_runs', ['user_id', 'created_at'])


def downgrade():
    op.drop_index('ix_teacher_ai_question_runs_user_created', table_name='teacher_ai_question_runs')
    op.drop_table('teacher_ai_question_runs')
