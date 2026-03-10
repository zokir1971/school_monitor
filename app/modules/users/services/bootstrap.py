# app/modules/users/services/bootstrap.py (назначение супер администратора при запуске платформы)

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.repo import UserRepo


class BootstrapService:
    # ---------------------------
    # BOOTSTRAP L0
    # ---------------------------
    @staticmethod
    async def can_bootstrap_superuser(db: AsyncSession) -> bool:
        return not await UserRepo.has_superuser(db)

    @staticmethod
    async def create_superuser(
            db: AsyncSession,
            *,
            username: str,
            password_hash: str,
            full_name: str,
            iin: str,
            email: str,
            phone: str,
    ) -> User:
        username = username.strip()
        full_name = full_name.strip()
        iin = iin.strip()
        email = email.strip().lower()
        phone = phone.strip()

        if not username:
            raise ValueError("Логин обязателен")
        if not full_name:
            raise ValueError("ФИО обязательно")
        if not iin:
            raise ValueError("ИИН обязателен")
        if not email:
            raise ValueError("Email обязателен")
        if not phone:
            raise ValueError("Телефон обязателен")

        # проверки уникальности ДО commit (чтобы дать красивую ошибку)
        if await UserRepo.get_by_username(db, username):
            raise ValueError("Такой логин уже существует")

        if await UserRepo.get_by_iin(db, iin):
            raise ValueError("Пользователь с таким ИИН уже существует")

        if await UserRepo.get_by_email(db, email):
            raise ValueError("Пользователь с таким email уже существует")

        if await UserRepo.get_by_phone(db, phone):
            raise ValueError("Пользователь с таким телефоном уже существует")

        user = User(
            username=username,
            full_name=full_name,
            iin=iin,
            email=email,
            phone=phone,
            password_hash=password_hash,
            is_active=True,
            role=UserRole.SUPERUSER,
        )

        await UserRepo.add(db, user)
        await db.commit()
        return user
