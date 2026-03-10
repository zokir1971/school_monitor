# app/modules/users/services/user_service.py (CRUD, профиль, смена пароля, активность)


from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    generate_registration_code,
    registration_code_lookup_hash,
)
from app.modules.org.repo import OrgRepo
from app.modules.users.enums import UserRole
from app.modules.users.models import User, RegistrationCode
from app.modules.users.repo import UserRepo, RegistrationCodeRepo
from app.common.time import utcnow
from app.modules.users.validators import validate_user_scope


class UserCrudService:
    # ---------------------------
    # ADMIN OFF BOARDING
    # ---------------------------
    @staticmethod
    async def deactivate_user(db: AsyncSession, *, actor: User, user_id: int) -> User:
        target = await UserRepo.get_by_id(db, user_id)
        if not target:
            raise ValueError("user not found")
        if actor.id == target.id:
            raise ValueError("нельзя отключить самого себя")

        # Минимальная политика: только SUPERUSER может отключать кого угодно.
        # (Если хочешь — расширим: REGION_ADMIN может отключать в своей области и т.д.)
        if actor.role != UserRole.SUPERUSER:
            raise ValueError("нет прав отключать пользователей")

        async with db.begin():
            target.is_active = False
        return target

    # ---------------------------
    # ISSUE CODE (верхний -> нижний)
    # ---------------------------
    @staticmethod
    async def issue_admin_code(
            db: AsyncSession,
            *,
            issuer: User,
            target_role: UserRole,
            region_id: int | None = None,
            district_id: int | None = None,
            school_id: int | None = None,
            quota: int = 1,
            expires_at: datetime | None = None,
    ) -> tuple[RegistrationCode, str]:
        """
        Возвращает (RegistrationCode, plain_code).
        plain_code показываем 1 раз на странице результата.
        """

        if quota <= 0:
            raise ValueError("quota должна быть > 0")

        # 1) строгая матрица "кто кому"
        allowed = {
            UserRole.SUPERUSER: {UserRole.REGION_ADMIN},
            UserRole.REGION_ADMIN: {UserRole.DISTRICT_ADMIN},
            UserRole.DISTRICT_ADMIN: {UserRole.SCHOOL_ADMIN},
            UserRole.SCHOOL_ADMIN: {UserRole.TEACHER},  # если учителя тоже через коды
        }
        if issuer.role not in allowed or target_role not in allowed[issuer.role]:
            raise ValueError("Нет прав выдавать код на эту роль")

        # 2) scope должен соответствовать target_role
        validate_user_scope(target_role, region_id, district_id, school_id)

        # 3) scope должен быть внутри зоны issuer
        if issuer.role == UserRole.SUPERUSER:
            # SUPERUSER выдаёт код REGION_ADMIN на любой region_id (но region_id обязателен)
            if target_role == UserRole.REGION_ADMIN and region_id is None:
                raise ValueError("region_id обязателен для REGION_ADMIN")

        elif issuer.role == UserRole.REGION_ADMIN:
            if issuer.region_id is None:
                raise ValueError("issuer.region_id is NULL")
            if district_id is None:
                raise ValueError("district_id обязателен для DISTRICT_ADMIN")
            ok = await OrgRepo.district_belongs_to_region(db, district_id=district_id, region_id=issuer.region_id)
            if not ok:
                raise ValueError("Район не принадлежит вашей области")

        elif issuer.role == UserRole.DISTRICT_ADMIN:
            if issuer.district_id is None:
                raise ValueError("issuer.district_id is NULL")
            if school_id is None:
                raise ValueError("school_id обязателен для SCHOOL_ADMIN")
            ok = await OrgRepo.school_belongs_to_district(db, school_id=school_id, district_id=issuer.district_id)
            if not ok:
                raise ValueError("Школа не принадлежит вашему району")

        elif issuer.role == UserRole.SCHOOL_ADMIN:
            if issuer.school_id is None:
                raise ValueError("issuer.school_id is NULL")
            # TEACHER должен быть только в своей школе
            if school_id != issuer.school_id:
                raise ValueError("Можно выдавать код только на свою школу")

        # 4) создаём код
        plain_code = generate_registration_code()
        lookup_hash = registration_code_lookup_hash(plain_code)
        now = utcnow()

        obj = RegistrationCode(
            code_lookup_hash=lookup_hash,
            target_role=target_role,
            region_id=region_id,
            district_id=district_id,
            school_id=school_id,
            issued_by_user_id=issuer.id,
            issued_at=now,
            quota_total=quota,
            quota_left=quota,
            is_active=True,
            expires_at=expires_at,
        )

        async with db.begin():
            await RegistrationCodeRepo.add(db, obj)

        return obj, plain_code

    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
        return await UserRepo.get_by_id(db, user_id)

    @staticmethod
    async def create_user(
            db: AsyncSession,
            *,
            username: str,
            password: str,
            role: UserRole,
            email: str | None = None,
            phone: str | None = None,
            region_id: int | None = None,
            district_id: int | None = None,
            school_id: int | None = None,
            is_active: bool = True,
    ) -> User:
        validate_user_scope(role, region_id, district_id, school_id)

        if await UserRepo.exists_by_username(db, username):
            raise ValueError("username уже занят")
        if email and await UserRepo.exists_by_email(db, email):
            raise ValueError("email уже используется")
        if phone and await UserRepo.exists_by_phone(db, phone):
            raise ValueError("phone уже используется")

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            email=email,
            phone=phone,
            region_id=region_id,
            district_id=district_id,
            school_id=school_id,
            is_active=is_active,
            created_at=utcnow(),
        )

        user = await UserRepo.add(db, user)
        return user
