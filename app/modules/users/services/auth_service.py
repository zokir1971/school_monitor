# app/modules/users/services/auth_service.py (логин/аутентификация)

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utcnow
from app.core.security import verify_password
from app.modules.users.models import User


class UserAuthService:
    # ---------------------------
    # AUTH
    # ---------------------------
    @staticmethod
    async def authenticate(
        db: AsyncSession,
        *,
        identifier: str,
        password: str,
    ) -> User | None:
        identifier = (identifier or "").strip()
        password = password or ""

        if not identifier or not password:
            return None

        from app.modules.users.repo import UserRepo
        user = await UserRepo.get_by_identifier(db, identifier)

        if not user or not user.is_active:
            return None

        if not await run_in_threadpool(verify_password, password, user.password_hash):
            return None

        user.last_login_at = utcnow()
        await db.flush()

        return user
