
from fastapi import HTTPException
from app.modules.users.models import User


def require_school_id(user: User) -> int:
    """
    Проверяет что пользователь привязан к школе
    и возвращает school_id.
    """
    school_id = getattr(user, "school_id", None)

    if not school_id:
        raise HTTPException(
            status_code=403,
            detail="Пользователь не привязан к школе"
        )

    return school_id
