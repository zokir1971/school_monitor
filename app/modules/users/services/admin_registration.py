# app/modules/users/services/admin_registration.py (регистрация по коду L1/L2/L3)

from __future__ import annotations

from starlette.concurrency import run_in_threadpool

from app.core.i18n import normalize_language

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, case, or_

from app.core.security import (
    hash_password,
    registration_code_lookup_hash,
)
from app.modules.org.models import Region, School, District
from app.modules.users.enums import UserRole
from app.modules.users.models import User, RegistrationCodeUse, RegistrationCode
from app.modules.users.repo import UserRepo, RegistrationCodeRepo
from app.common.time import utcnow
from app.modules.users.validators import validate_user_scope


class AdminRegistrationService:
    # ---------------------------
    # REGISTER BY CODE
    # ---------------------------
    @staticmethod
    async def register_admin_with_code(
            db: AsyncSession,
            *,
            code: str,
            username: str,
            password: str,
            full_name: str | None = None,
            iin: str | None = None,
            selected_region_id: int | None = None,
            email: str | None = None,
            phone: str | None = None,
            ui_language: str | None = None,
    ) -> User:
        code_norm = code.strip().upper()
        lookup_hash = registration_code_lookup_hash(code_norm)
        now = utcnow()

        # ---------------------------
        # ВСЁ делаем в одной транзакции
        # + блокируем строку кода, чтобы не было гонок по quota_left
        # ---------------------------
        async with db.begin():
            # Same lock order as issuance and school transfer: school, then code.
            code_school_id = await db.scalar(select(RegistrationCode.school_id).where(
                RegistrationCode.code_lookup_hash == lookup_hash))
            if code_school_id is not None:
                await db.execute(select(School.__table__.c.id).where(
                    School.__table__.c.id == code_school_id).with_for_update())
            # 1) Берём код с блокировкой
            rc = await RegistrationCodeRepo.get_by_lookup_hash_for_update(db, lookup_hash)
            if not rc:
                raise ValueError("Неверный код")

            now = utcnow()
            # 2) Проверки валидности кода (уже внутри транзакции)
            if not rc.is_active or rc.revoked_at is not None:
                raise ValueError("Код не активен или отозван")
            expires_at = rc.expires_at
            if expires_at is not None and expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=now.tzinfo)
            if expires_at is not None and expires_at <= now:
                raise ValueError("Срок действия кода истёк")
            if rc.quota_left <= 0:
                raise ValueError("Квота по коду исчерпана")

            target_role = rc.target_role

            # 3) Scope вычисляем
            user_region_id = None
            user_district_id = None
            user_school_id = None

            if target_role == UserRole.REGION_ADMIN:
                if selected_region_id is None:
                    raise ValueError("Выберите область")
                if rc.region_id is not None and selected_region_id != rc.region_id:
                    raise ValueError("Выбранная область не соответствует коду")

                region = (await db.execute(select(Region.id).where(Region.id == selected_region_id))).first()
                if not region:
                    raise ValueError("Область не найдена")

                user_region_id = selected_region_id

            elif target_role == UserRole.DISTRICT_ADMIN:

                if rc.district_id is None:
                    raise ValueError("Код повреждён: нет district_id")

                d = (await db.execute(select(District.id).where(District.id == rc.district_id))).first()

                if not d:
                    raise ValueError("Район по коду не найден")

                # users single-scope: только district_id

                user_region_id = None

                user_district_id = d.id

                user_school_id = None

            elif target_role == UserRole.SCHOOL_ADMIN:

                if rc.school_id is None:
                    raise ValueError("Код повреждён: нет school_id")

                s = (await db.execute(select(School.id).where(School.id == rc.school_id))).first()

                if not s:
                    raise ValueError("Школа по коду не найдена")

                # ✅ users single-scope: только school_id

                user_region_id = None

                user_district_id = None

                user_school_id = s.id

            elif target_role == UserRole.TEACHER:
                if rc.school_id is None:
                    raise ValueError("Код повреждён: нет school_id")
                user_school_id = rc.school_id

            else:
                raise ValueError("Этот код не предназначен для регистрации")

            # 4) Финальная проверка scope
            validate_user_scope(target_role, user_region_id, user_district_id, user_school_id)

            # 5) Уникальности — тоже внутри транзакции (чтобы не было гонок)
            username_norm = username.strip()
            if await UserRepo.exists_by_username(db, username_norm):
                raise ValueError("username уже занят")
            if email and await UserRepo.exists_by_email(db, email.strip().lower()):
                raise ValueError("email уже используется")
            if phone and await UserRepo.exists_by_phone(db, phone.strip()):
                raise ValueError("phone уже используется")

            # 6) Создаём пользователя (flush внутри add)
            user = User(
                ui_language=normalize_language(ui_language),
                username=username_norm,
                full_name=full_name.strip() if full_name else None,
                iin=iin.strip() if iin else None,
                password_hash=await run_in_threadpool(hash_password, password),
                role=target_role,
                email=email.strip().lower() if email else None,
                phone=phone.strip() if phone else None,
                region_id=user_region_id,
                district_id=user_district_id,
                school_id=user_school_id,
                is_active=True,
                created_at=now,
            )
            user = await UserRepo.add(db, user)

            # 7) Списываем квоту и пишем аудит
            C = type(rc).__table__
            remaining = (await db.execute(update(C).where(
                C.c.id == rc.id, C.c.is_active.is_(True), C.c.revoked_at.is_(None),
                C.c.quota_left > 0, or_(C.c.expires_at.is_(None), C.c.expires_at > now),
            ).values(quota_left=C.c.quota_left - 1,
                     is_active=case((C.c.quota_left > 1, True), else_=False))
            .returning(C.c.quota_left))).scalar_one_or_none()
            if remaining is None:
                raise ValueError("Код уже использован, отозван или истёк")

            use = RegistrationCodeUse(
                code_id=rc.id,
                used_by_user_id=user.id,
                used_at=now,
            )
            await RegistrationCodeRepo.add_use(db, use)

            # commit сделает контекстный менеджер db.begin()
            # import logging
            # log = logging.getLogger(__name__)
            # log.info("REGISTER_BY_CODE role=%s code=%s", target_role, code)
        return user
