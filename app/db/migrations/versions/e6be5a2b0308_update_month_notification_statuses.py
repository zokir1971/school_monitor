"""update month notification statuses

Revision ID: e6be5a2b0308
Revises: 7dd05044ddca
Create Date: 2026-08-05 23:39:18.303166

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e6be5a2b0308'
down_revision: Union[str, None] = '7dd05044ddca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_ENUM = "month_plan_notification_status_enum"
NEW_ENUM = "month_plan_notification_status_enum_new"


def upgrade() -> None:
    """
    Переход:

        pending
        opened    -> sent
        confirmed -> accepted
    """

    # Создать новый ENUM
    op.execute(f"""
        CREATE TYPE {NEW_ENUM} AS ENUM (
            'pending',
            'sent',
            'accepted'
        );
    """)

    # Временно перевести колонку в TEXT
    op.execute(f"""
        ALTER TABLE school_month_plan_notifications
        ALTER COLUMN status
        TYPE TEXT
        USING status::TEXT;
    """)

    # Обновить значения
    op.execute("""
        UPDATE school_month_plan_notifications
        SET status =
            CASE status
                WHEN 'opened' THEN 'sent'
                WHEN 'confirmed' THEN 'accepted'
                ELSE status
            END;
    """)

    # Удалить старый ENUM
    op.execute(f"""
        DROP TYPE {OLD_ENUM};
    """)

    # Переименовать новый ENUM
    op.execute(f"""
        ALTER TYPE {NEW_ENUM}
        RENAME TO {OLD_ENUM};
    """)

    # Вернуть колонку к ENUM
    op.execute(f"""
        ALTER TABLE school_month_plan_notifications
        ALTER COLUMN status
        TYPE {OLD_ENUM}
        USING status::{OLD_ENUM};
    """)


def downgrade() -> None:
    """
    Обратный переход:

        pending
        sent      -> opened
        accepted  -> confirmed
    """

    op.execute("""
        CREATE TYPE month_plan_notification_status_enum_old AS ENUM (
            'pending',
            'opened',
            'confirmed'
        );
    """)

    op.execute("""
        ALTER TABLE school_month_plan_notifications
        ALTER COLUMN status
        TYPE TEXT
        USING status::TEXT;
    """)

    op.execute("""
        UPDATE school_month_plan_notifications
        SET status =
            CASE status
                WHEN 'sent' THEN 'opened'
                WHEN 'accepted' THEN 'confirmed'
                ELSE status
            END;
    """)

    op.execute(f"""
        DROP TYPE {OLD_ENUM};
    """)

    op.execute(f"""
        ALTER TYPE month_plan_notification_status_enum_old
        RENAME TO {OLD_ENUM};
    """)

    op.execute(f"""
        ALTER TABLE school_month_plan_notifications
        ALTER COLUMN status
        TYPE {OLD_ENUM}
        USING status::{OLD_ENUM};
    """)
