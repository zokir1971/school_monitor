# app/modules/users/pero.py
from __future__ import annotations

from sqlalchemy import select, exists, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User, RegistrationCode, RegistrationCodeUse
from app.modules.users.enums import UserRole


class UserRepo:
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
        res = await db.execute(select(User).where(User.id == user_id))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> User | None:
        res = await db.execute(select(User).where(User.username == username))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_iin(db: AsyncSession, iin: str) -> User | None:
        res = await db.execute(select(User).where(User.iin == iin))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_identifier(db: AsyncSession, identifier: str) -> User | None:
        identifier = identifier.strip()

        res = await db.execute(
            select(User).where(
                or_(
                    User.username == identifier,
                    User.iin == identifier,
                )
            )
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> User | None:
        res = await db.execute(select(User).where(User.email == email))
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_phone(db: AsyncSession, phone: str) -> User | None:
        res = await db.execute(select(User).where(User.phone == phone))
        return res.scalar_one_or_none()

    @staticmethod
    async def exists_by_username(db: AsyncSession, username: str) -> bool:
        res = await db.execute(select(User.id).where(User.username == username))
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def exists_by_email(db: AsyncSession, email: str) -> bool:
        res = await db.execute(select(User.id).where(User.email == email))
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def exists_by_phone(db: AsyncSession, phone: str) -> bool:
        res = await db.execute(select(User.id).where(User.phone == phone))
        return res.scalar_one_or_none() is not None

    @staticmethod
    async def has_superuser(db: AsyncSession) -> bool:
        q = await db.execute(select(exists().where(User.role == UserRole.SUPERUSER)))
        return bool(q.scalar())

    @staticmethod
    async def add(db: AsyncSession, user: User) -> User:
        db.add(user)
        await db.flush()
        await db.refresh(user)
        return user


class RegistrationCodeRepo:
    @staticmethod
    async def get_by_lookup_hash(db: AsyncSession, lookup_hash: str) -> RegistrationCode | None:
        res = await db.execute(
            select(RegistrationCode).where(RegistrationCode.code_lookup_hash == lookup_hash)
        )
        return res.scalar_one_or_none()

    @staticmethod
    async def add(db: AsyncSession, obj: RegistrationCode) -> RegistrationCode:
        db.add(obj)
        await db.flush()
        await db.refresh(obj)
        return obj

    @staticmethod
    async def add_use(db: AsyncSession, use: RegistrationCodeUse) -> RegistrationCodeUse:
        db.add(use)
        await db.flush()
        await db.refresh(use)
        return use

    @staticmethod
    async def get_by_lookup_hash_for_update(db: AsyncSession, lookup_hash: str) -> RegistrationCode | None:
        res = await db.execute(
            select(RegistrationCode)
            .where(RegistrationCode.code_lookup_hash == lookup_hash)
            .with_for_update()
        )
        return res.scalar_one_or_none()
