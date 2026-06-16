"""add report signature tokens

Revision ID: 7c6f95ef9eca
Revises: 852f0040706e
Create Date: 2026-06-09 07:36:47.806895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7c6f95ef9eca'
down_revision: Union[str, None] = '852f0040706e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'report_signature_tokens',

        sa.Column('id', sa.Integer(), nullable=False),

        sa.Column('code', sa.String(length=32), nullable=False),

        sa.Column('token', sa.Text(), nullable=False),

        sa.Column('report_type', sa.String(length=64), nullable=False),

        sa.Column('report_id', sa.Integer(), nullable=True),

        sa.Column('document_id', sa.Integer(), nullable=True),

        sa.Column('is_active', sa.Boolean(), nullable=False),

        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ['document_id'],
            ['task_execution_documents.id'],
            ondelete='CASCADE',
        ),

        sa.PrimaryKeyConstraint('id'),

        sa.UniqueConstraint('code')
    )

    op.create_index(
        'ix_report_signature_tokens_code_active',
        'report_signature_tokens',
        ['code', 'is_active'],
        unique=False,
    )

    op.create_index(
        'ix_report_signature_tokens_document',
        'report_signature_tokens',
        ['document_id'],
        unique=False,
    )

    op.create_index(
        'ix_report_signature_tokens_report',
        'report_signature_tokens',
        ['report_type', 'report_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_report_signature_tokens_report',
        table_name='report_signature_tokens',
    )

    op.drop_index(
        'ix_report_signature_tokens_document',
        table_name='report_signature_tokens',
    )

    op.drop_index(
        'ix_report_signature_tokens_code_active',
        table_name='report_signature_tokens',
    )

    op.drop_table('report_signature_tokens')
