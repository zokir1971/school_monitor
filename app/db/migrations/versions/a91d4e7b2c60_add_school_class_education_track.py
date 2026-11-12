"""Add school class education track.

Revision ID: a91d4e7b2c60
Revises: f72a8c16d903
"""

from alembic import op
import sqlalchemy as sa


revision = "a91d4e7b2c60"
down_revision = "f72a8c16d903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())

    columns = {
        column["name"]: column
        for column in inspector.get_columns(
            "school_classes",
            schema="public",
        )
    }

    if "education_track" not in columns:
        op.add_column(
            "school_classes",
            sa.Column(
                "education_track",
                sa.String(length=10),
                nullable=True,
            ),
            schema="public",
        )
    else:
        column = columns["education_track"]
        if (
            not isinstance(column["type"], sa.String)
            or column["type"].length != 10
            or not column["nullable"]
        ):
            raise RuntimeError(
                "Existing education_track column differs "
                "from the expected nullable VARCHAR(10)."
            )

    constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "school_classes",
            schema="public",
        )
    }

    if "ck_school_class_education_track" not in constraints:
        op.create_check_constraint(
            "ck_school_class_education_track",
            "school_classes",
            "education_track IS NULL OR "
            "(grade_level IN (10, 11) "
            "AND education_track IN ('emn', 'ogn'))",
            schema="public",
        )


def downgrade() -> None:
    op.drop_constraint(
        "ck_school_class_education_track",
        "school_classes",
        type_="check",
        schema="public",
    )
    op.drop_column(
        "school_classes",
        "education_track",
        schema="public",
    )
