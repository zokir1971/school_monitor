"""Persist school activity schema; retain previously collected local history."""
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "f44b104ac644"
down_revision = "f43b104ac643"
branch_labels = None
depends_on = None

SCHEMA = "public"


def activity_tables():
    metadata = sa.MetaData(schema=SCHEMA)
    # Resolve the FK without importing application models or creating schools.
    sa.Table("schools", metadata, sa.Column("id", sa.Integer, primary_key=True))
    days = sa.Table(
        "school_activity_days", metadata,
        sa.Column("school_id", sa.Integer, sa.ForeignKey("public.schools.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("module", sa.String(24), primary_key=True),
        sa.Column("first_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("module IN ('login','planning','tasks','reports','reviews','staff','education','assessment')", name="ck_school_activity_module"),
        sa.Index("ix_school_activity_period", "day", "school_id"),
    )
    state = sa.Table(
        "school_activity_state", metadata,
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_school_activity_singleton"),
    )
    return days, state


def validate_table(bind, table):
    inspector = sa.inspect(bind)
    actual = {column["name"]: column for column in inspector.get_columns(table.name, schema=SCHEMA)}
    if set(actual) != set(table.c.keys()):
        raise RuntimeError(f"Unexpected columns in public.{table.name}; no existing data will be replaced")
    for expected in table.c:
        column = actual[expected.name]
        if column["nullable"] != expected.nullable or column["type"]._type_affinity is not expected.type._type_affinity:
            raise RuntimeError(f"Unexpected type/nullability: {table.name}.{expected.name}")
        if isinstance(expected.type, sa.String) and column["type"].length != expected.type.length:
            raise RuntimeError(f"Unexpected string length: {table.name}.{expected.name}")
        if bind.dialect.name == "postgresql" and isinstance(expected.type, sa.DateTime) and not column["type"].timezone:
            raise RuntimeError(f"Timestamp must have time zone: {table.name}.{expected.name}")
    if inspector.get_pk_constraint(table.name, schema=SCHEMA)["constrained_columns"] != list(table.primary_key.columns.keys()):
        raise RuntimeError(f"Unexpected primary key: {table.name}")
    expected_checks = {c.name for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    if not expected_checks.issubset({c["name"] for c in inspector.get_check_constraints(table.name, schema=SCHEMA)}):
        raise RuntimeError(f"Missing check constraint: {table.name}")
    if table.name == "school_activity_days":
        foreign_keys = inspector.get_foreign_keys(table.name, schema=SCHEMA)
        if not any(f["constrained_columns"] == ["school_id"] and f["referred_table"] == "schools"
                   and f.get("referred_schema") in (None, SCHEMA) and f["referred_columns"] == ["id"]
                   and f.get("options", {}).get("ondelete", "").upper() == "CASCADE" for f in foreign_keys):
            raise RuntimeError("Unexpected school activity foreign key")


def upgrade():
    bind = op.get_bind()
    days, state = activity_tables()
    # The stage285 setup script may already have created these tables locally.
    for table in (days, state):
        if not sa.inspect(bind).has_table(table.name, schema=SCHEMA):
            table.create(bind)
        validate_table(bind, table)
    indexes = sa.inspect(bind).get_indexes(days.name, schema=SCHEMA)
    existing = next((i for i in indexes if i["name"] == "ix_school_activity_period"), None)
    if existing and (existing["column_names"] != ["day", "school_id"] or existing["unique"]):
        raise RuntimeError("Unexpected ix_school_activity_period definition")
    if existing is None:
        next(iter(days.indexes)).create(bind)
    bind.execute(sa.text(
        "INSERT INTO public.school_activity_state (id, started_at) VALUES (1, :started_at) "
        "ON CONFLICT (id) DO NOTHING"
    ), {"started_at": datetime.now(timezone.utc)})


def downgrade():
    raise RuntimeError("Activity history is retained. Roll back application code without dropping activity tables.")
