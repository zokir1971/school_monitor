"""add text segments to question bank items

Revision ID: 5869f896b73b
Revises: be80f5235454
Create Date: 2026-09-27 15:29:40.575129

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5869f896b73b'
down_revision: Union[str, None] = 'be80f5235454'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Добавляем колонку.
    op.add_column(
        "question_bank_items",
        sa.Column(
            "text_segments",
            postgresql.JSONB(
                astext_type=sa.Text(),
            ),
            server_default=sa.text(
                "'[]'::jsonb"
            ),
            nullable=False,
        ),
    )

    # 2. Существующие задания переводим
    #    на новый rich-content контракт.
    op.execute(
        """
        UPDATE question_bank_items
        SET text_segments =
            jsonb_build_array(
                jsonb_build_object(
                    'type', 'text',
                    'text', text
                )
            )
        WHERE
            text_segments = '[]'::jsonb
            AND text IS NOT NULL
            AND btrim(text) <> '';
        """
    )


def downgrade() -> None:
    op.drop_column(
        "question_bank_items",
        "text_segments",
    )