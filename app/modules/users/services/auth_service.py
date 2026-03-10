# app/modules/users/services/auth_service.py (логин/аутентификация)

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import verify_password
from app.modules.users.models import User
from app.modules.users.repo import UserRepo
from app.common.time import utcnow


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

        stmt = select(User)

        # если введено 12 цифр — считаем это ИИН
        if identifier.isdigit() and len(identifier) == 12:
            stmt = stmt.where(User.iin == identifier)
        else:
            stmt = stmt.where(User.username == identifier)

        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user or not user.is_active:
            return None

        if not verify_password(password, user.password_hash):
            return None

        user.last_login_at = utcnow()
        await db.flush()

        return user
