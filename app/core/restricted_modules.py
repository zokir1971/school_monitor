"""Gate unfinished modules using the authenticated global role, not workspace."""
from fastapi import Depends, HTTPException

from app.core.feature_flags import restricted_modules_allowed
from app.modules.users.deps import get_current_user
from app.modules.users.models import User


async def require_restricted_modules(user: User = Depends(get_current_user)) -> User:
    if not restricted_modules_allowed(user):
        raise HTTPException(status_code=403, detail="Раздел доступен только супер администратору. / Бөлім тек супер әкімшіге қолжетімді.")
    return user


require_restricted_modules.feature_key = "superuser_modules"
