"""Add scientific-methodical deputy role without rewriting existing assignments."""
from alembic import op

revision = 'f50b104ac650'
down_revision = 'f49b104ac649'
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE public.responsible_role_enum ADD VALUE IF NOT EXISTS 'd_scientific_methodical'")


def downgrade():
    raise RuntimeError('The new role is retained in PostgreSQL. Do not drop/recreate responsible_role_enum; preserve assignments and check usage before reverting application code.')
