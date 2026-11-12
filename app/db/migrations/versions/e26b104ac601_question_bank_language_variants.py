"""One review lifecycle for paired RU/KZ task content."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='e26b104ac601'
down_revision='d94f103ac527'
branch_labels=None
depends_on=None

def upgrade():
    # Existing tasks stay valid single-language records; no content is backfilled.
    op.add_column('question_bank_items',sa.Column('requires_bilingual',sa.Boolean(),server_default=sa.false(),nullable=False))
    op.create_table('question_bank_language_variants',
        sa.Column('item_id',sa.Integer(),sa.ForeignKey('question_bank_items.id',ondelete='CASCADE'),primary_key=True),
        sa.Column('language',sa.String(2),primary_key=True),
        sa.Column('payload',postgresql.JSONB(),nullable=False),
        sa.Column('source_fingerprint',sa.String(64),nullable=False),
        sa.Column('edited_by_user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='SET NULL')),
        sa.Column('updated_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.CheckConstraint("language IN ('ru','kk')",name='ck_qb_variant_language'))

def downgrade():
    op.drop_table('question_bank_language_variants')
    op.drop_column('question_bank_items','requires_bilingual')
