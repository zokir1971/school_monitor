"""Independent user interface language; no assessment data is changed."""
from alembic import op
import sqlalchemy as sa

revision = "d94f103ac527"
down_revision = "c83e9f40b216"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("ui_language", sa.String(2), nullable=True))
    op.create_check_constraint("ck_users_ui_language", "users",
                               "ui_language IS NULL OR ui_language IN ('ru', 'kk')")


def downgrade():
    op.drop_constraint("ck_users_ui_language", "users", type_="check")
    op.drop_column("users", "ui_language")
