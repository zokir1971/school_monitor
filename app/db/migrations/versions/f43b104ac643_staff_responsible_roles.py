"""Add four administrative roles without changing existing values or assignments."""
from alembic import op

revision = 'f43b104ac643'
down_revision = 'f42b104ac642'
branch_labels = None
depends_on = None

NEW_ROLES = ('internat_head', 'd_informatization', 'd_foreign_language', 'd_primary_classes')


def upgrade():
    # Commit enum additions before any subsequent migration can use their values.
    with op.get_context().autocommit_block():
        for role in NEW_ROLES:
            op.execute(f"ALTER TYPE public.responsible_role_enum ADD VALUE IF NOT EXISTS '{role}'")


def downgrade():
    # PostgreSQL cannot remove an enum value safely in place. Never rewrite history.
    raise RuntimeError('Enum additions are retained. Reassign new roles before reverting application code.')
