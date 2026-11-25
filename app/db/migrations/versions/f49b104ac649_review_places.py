"""Extend review places without recreating the type or changing saved protocols."""
from alembic import op

revision='f49b104ac649'
down_revision='f48b104ac648'
branch_labels=None
depends_on=None

NEW_PLACES=('administrative_meeting','scientific_academy_council',
            'class_teacher_meeting','student_self_government')


def upgrade():
    # The existing enum is shared by annual/monthly places and review protocols.
    # Values must be committed before later statements can use them.
    with op.get_context().autocommit_block():
        for value in NEW_PLACES:
            op.execute(f"ALTER TYPE public.review_place ADD VALUE IF NOT EXISTS '{value}'")


def downgrade():
    # PostgreSQL cannot remove enum values safely in place. Retain all history.
    raise RuntimeError('New review-place values are retained. Reassign them before reverting application code; do not drop or recreate review_place.')
