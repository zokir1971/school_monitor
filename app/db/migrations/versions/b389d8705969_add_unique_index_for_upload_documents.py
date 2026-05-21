"""add unique index for upload documents

Revision ID: b389d8705969
Revises: 2e55f7a3c351
Create Date: 2026-04-22 23:17:38.662737

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b389d8705969'
down_revision: Union[str, None] = '2e55f7a3c351'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.execute("""
        CREATE UNIQUE INDEX uq_final_upload_doc
        ON task_execution_documents (
            month_item_id,
            required_document_id,
            document_type,
            source
        )
        WHERE source = 'upload';
    """)


def downgrade():
    op.execute("""
        DROP INDEX IF EXISTS uq_final_upload_doc;
    """)
