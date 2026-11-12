"""add language_skills to objective skills

Revision ID: e54f155f52d9
Revises: c84e21d0a7b6
Create Date: 2026-10-17 08:15:51.018458

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e54f155f52d9'
down_revision: Union[str, None] = 'c84e21d0a7b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.drop_constraint(
        'ck_lo_language_skill',
        'learning_objectives',
        type_='check',
    )
    op.create_check_constraint(
        'ck_lo_language_skill',
        'learning_objectives',
        "language_skill IS NULL OR language_skill IN ("
        "'listening','speaking','reading','writing',"
        "'listening_speaking','language_norms','language_skills')",
    )


def downgrade():
    # Откат остановится, если уже существуют цели с language_skills.
    # Это предотвращает потерю различия между двумя навыками.
    op.drop_constraint(
        'ck_lo_language_skill',
        'learning_objectives',
        type_='check',
    )
    op.create_check_constraint(
        'ck_lo_language_skill',
        'learning_objectives',
        "language_skill IS NULL OR language_skill IN ("
        "'listening','speaking','reading','writing',"
        "'listening_speaking','language_norms')",
    )
