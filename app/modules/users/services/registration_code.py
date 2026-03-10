# app/modules/users/services/registration_code.py

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    registration_code_lookup_hash,
)
from app.modules.org.models import District
from app.modules.users.enums import UserRole
from app.modules.users.models import RegistrationCode
from app.modules.users.repo import RegistrationCodeRepo
from app.modules.users.validators import _make_human_code
from app.common.time import utcnow


class RegistrationCodeService:
    @staticmethod
    async def _issue_code(
            db: AsyncSession,
            *,
            prefix: str,  # "L1" / "L2" / "L3"
            target_role: UserRole,  # REGION_ADMIN / DISTRICT_ADMIN / SCHOOL_ADMIN
            issued_by_user_id: int,
            quota_total: int = 1,
            expires_days: int | None = 30,
            region_id: int | None = None,
            district_id: int | None = None,
            school_id: int | None = None,
    ) -> tuple[str, RegistrationCode]:
        """
        Универсальная выдача кода:
        - отзовёт предыдущий активный НЕИСПОЛЬЗОВАННЫЙ код для той же цели
        - создаст новый короткий код (prefix-XXXX)
        """

        if quota_total < 1:
            raise ValueError("quota_total должен быть >= 1")

        # --- 0) проверка, что цель задана корректно ---
        # L1: нужен region_id
        if target_role == UserRole.REGION_ADMIN and not region_id:
            raise ValueError("Для L1 нужен region_id")
        # L2: нужен district_id
        if target_role == UserRole.DISTRICT_ADMIN and not district_id:
            raise ValueError("Для L2 нужен district_id")
        # L3: нужен school_id
        if target_role == UserRole.SCHOOL_ADMIN and not school_id:
            raise ValueError("Для L3 нужен school_id")

        # --- 1) ищем предыдущий активный код на ту же цель ---
        q = select(RegistrationCode).where(
            RegistrationCode.target_role == target_role,
            RegistrationCode.is_active == True,  # noqa: E712
            RegistrationCode.revoked_at.is_(None),
        )

        if region_id is not None:
            q = q.where(RegistrationCode.region_id == region_id)
        if district_id is not None:
            q = q.where(RegistrationCode.district_id == district_id)
        if school_id is not None:
            q = q.where(RegistrationCode.school_id == school_id)

        prev = await db.scalar(q.order_by(RegistrationCode.id.desc()).limit(1))

        # --- 2) отзываем, если не использовался ---
        if prev:
            if prev.quota_left == prev.quota_total:
                prev.is_active = False
                prev.revoked_at = utcnow()
            else:
                raise ValueError(
                    "По этой цели код уже использовали (квота частично потрачена). "
                    "Пере выпуск запрещён."
                )

        # --- 3) генерируем новый короткий код ---
        raw_code = _make_human_code(prefix=prefix, group_len=4)  # Lx-XXXX
        lookup = registration_code_lookup_hash(raw_code)  # важно: должно совпадать с preview_code

        expires_at: datetime | None = None
        if expires_days is not None:
            expires_at = utcnow() + timedelta(days=expires_days)

        obj = RegistrationCode(
            code_lookup_hash=lookup,
            target_role=target_role,
            region_id=region_id if target_role == UserRole.REGION_ADMIN else None,
            district_id=district_id if target_role == UserRole.DISTRICT_ADMIN else None,
            school_id=school_id if target_role == UserRole.SCHOOL_ADMIN else None,
            issued_by_user_id=issued_by_user_id,
            quota_total=quota_total,
            quota_left=quota_total,
            is_active=True,
            expires_at=expires_at,
        )

        await RegistrationCodeRepo.add(db, obj)
        await db.commit()

        return raw_code, obj

    @staticmethod
    async def issue_l1_code(
            db: AsyncSession,
            *,
            issued_by_user_id: int,
            region_id: int,
            quota_total: int = 1,
            expires_days: int | None = 30,
    ) -> tuple[str, RegistrationCode]:
        return await RegistrationCodeService._issue_code(
            db,
            prefix="L1",
            target_role=UserRole.REGION_ADMIN,
            issued_by_user_id=issued_by_user_id,
            region_id=region_id,
            quota_total=quota_total,
            expires_days=expires_days,
        )

    @staticmethod
    async def issue_l2_code(
            db: AsyncSession,
            *,
            issued_by_user_id: int,
            region_id: int,
            district_id: int,
            quota_total: int = 1,
            expires_days: int | None = 30,
    ) -> tuple[str, RegistrationCode]:

        # (желательно) проверить что район принадлежит региону
        d = await db.get(District, district_id)
        if not d or d.region_id != region_id:
            raise ValueError("Район не относится к вашему региону")

        raw_code = _make_human_code(prefix="L2", group_len=4)
        lookup = registration_code_lookup_hash(raw_code)

        expires_at = None
        if expires_days is not None:
            expires_at = utcnow() + timedelta(days=expires_days)

        obj = RegistrationCode(
            code_lookup_hash=lookup,
            target_role=UserRole.DISTRICT_ADMIN,
            region_id=None,  # ✅ важно
            district_id=district_id,  # ✅ важно
            school_id=None,
            issued_by_user_id=issued_by_user_id,
            quota_total=quota_total,
            quota_left=quota_total,
            is_active=True,
            expires_at=expires_at,
        )

        await RegistrationCodeRepo.add(db, obj)
        await db.commit()
        return raw_code, obj

    @staticmethod
    async def issue_l3_code(
            db: AsyncSession,
            *,
            issued_by_user_id: int,
            school_id: int,
            quota_total: int = 1,
            expires_days: int | None = 30,
    ) -> tuple[str, RegistrationCode]:
        return await RegistrationCodeService._issue_code(
            db,
            prefix="L3",
            target_role=UserRole.SCHOOL_ADMIN,
            issued_by_user_id=issued_by_user_id,
            school_id=school_id,
            quota_total=quota_total,
            expires_days=expires_days,
        )

    @staticmethod
    async def preview_code(db: AsyncSession, *, invite_code: str) -> RegistrationCode:
        # 1) Получаем lookup hash единым способом (через core.security)
        invite_code = invite_code.strip().upper()
        lookup = registration_code_lookup_hash(invite_code)

        # 2) Ищем запись кода в БД по детерминированному хэшу
        code_obj = await RegistrationCodeRepo.get_by_lookup_hash(db, lookup)
        if not code_obj:
            raise ValueError("Код не найден")

        # 3) Проверяем флаги активности/отзыва
        if not code_obj.is_active or code_obj.revoked_at is not None:
            raise ValueError("Код отключён")

        # 4) Проверяем срок действия
        if code_obj.expires_at is not None and code_obj.expires_at <= utcnow():
            raise ValueError("Срок действия кода истёк")

        # 5) Проверяем квоту
        if code_obj.quota_left <= 0:
            raise ValueError("Лимит регистраций по коду исчерпан")

        return code_obj
