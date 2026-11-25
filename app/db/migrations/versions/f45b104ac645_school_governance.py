"""Separate school location from administrative governance.

Existing school IDs, users, plans and registration-code history are retained.
"""
from alembic import op
import sqlalchemy as sa

revision = "f45b104ac645"
down_revision = "f44b104ac644"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("schools") as batch:
        batch.add_column(sa.Column("governance_level", sa.String(16), nullable=False, server_default="district"))
        batch.create_check_constraint("ck_school_governance_level", "governance_level IN ('district', 'region')")
        batch.create_index("ix_school_governance_district", ["governance_level", "district_id"], unique=False)
    op.create_table("school_governance_changes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("school_id", sa.Integer, sa.ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("actor_user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("old_level", sa.String(16), nullable=False),
        sa.Column("new_level", sa.String(16), nullable=False),
        sa.Column("old_district_id", sa.Integer, nullable=False),
        sa.Column("new_district_id", sa.Integer, nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_school_governance_changes_school_id", "school_governance_changes", ["school_id"])


def downgrade():
    # Restoring geography-only permissions while regional schools remain would
    # silently grant their district administrators authority over those schools.
    if op.get_bind().execute(sa.text("SELECT 1 FROM schools WHERE governance_level <> 'district' LIMIT 1")).first():
        raise RuntimeError("Сначала переведите областные школы на районное подчинение через форму школы")
    op.drop_index("ix_school_governance_changes_school_id", table_name="school_governance_changes")
    op.drop_table("school_governance_changes")
    with op.batch_alter_table("schools") as batch:
        batch.drop_index("ix_school_governance_district")
        batch.drop_constraint("ck_school_governance_level", type_="check")
        batch.drop_column("governance_level")
