"""add teacher user role

Revision ID: eaa3a0589616
Revises: 704452ea1e37
Create Date: 2026-08-29 06:56:18.354404

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'eaa3a0589616'
down_revision: Union[str, None] = '704452ea1e37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_ROLE_ENUM_NAME = "user_role"
TEACHER_VALUE = "teacher"


def upgrade() -> None:
    """
    Добавляет роль teacher в PostgreSQL ENUM user_role.

    IF NOT EXISTS делает миграцию безопасной
    при повторной проверке окружения.
    """

    op.execute(
        f"""
        ALTER TYPE {USER_ROLE_ENUM_NAME}
        ADD VALUE IF NOT EXISTS '{TEACHER_VALUE}'
        """
    )


def downgrade() -> None:
    """
    PostgreSQL не поддерживает безопасное
    DROP VALUE из ENUM.

    Поэтому downgrade намеренно ничего не делает.

    Удаление значения ENUM потребовало бы:
        1. создания нового enum;
        2. преобразования users.role;
        3. удаления старого enum;
        4. переименования нового enum.

    Для production это неоправданно рискованно.
    """
    pass
