"""fix document_type enum mismatch

Revision ID: 32bfd7789ef1
Revises: 14dafbca9bc8
Create Date: 2026-04-12 08:55:41.112317

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '32bfd7789ef1'
down_revision: Union[str, None] = '14dafbca9bc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # переводим колонку на правильный enum
    op.execute("""
        ALTER TABLE task_execution_documents
        ALTER COLUMN document_type
        TYPE document_type
        USING document_type::text::document_type
    """)

    # удаляем старый enum, если он больше не используется
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_attribute a
                JOIN pg_type t ON t.oid = a.atttypid
                WHERE t.typname = 'document_type_enum'
            ) THEN
                DROP TYPE document_type_enum;
            END IF;
        END$$;
    """)


def downgrade():
    op.execute("""
        CREATE TYPE document_type_enum AS ENUM (
            'plan',
            'protocol',
            'act',
            'report',
            'reference',
            'other'
        )
    """)

    op.execute("""
        ALTER TABLE task_execution_documents
        ALTER COLUMN document_type
        TYPE document_type_enum
        USING document_type::text::document_type_enum
    """)
