# app/modules/users/services/admin_registration.py (регистрация по коду L1/L2/L3)

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    registration_code_lookup_hash,
)
from app.modules.org.models import Region, School, District
from app.modules.users.enums import UserRole
from app.modules.users.models import User, RegistrationCodeUse
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
            selected_district_id: int | None = None,
            selected_school_id: int | None = None,
            email: str | None = None,
            phone: str | None = None,
    ) -> User:
        code_norm = code.strip().upper()
        lookup_hash = registration_code_lookup_hash(code_norm)
        now = utcnow()

        # ---------------------------
        # ВСЁ делаем в одной транзакции
        # + блокируем строку кода, чтобы не было гонок по quota_left
        # ---------------------------
        async with db.begin():
            # 1) Берём код с блокировкой
            rc = await RegistrationCodeRepo.get_by_lookup_hash_for_update(db, lookup_hash)
            if not rc:
                raise ValueError("Неверный код")

            # 2) Проверки валидности кода (уже внутри транзакции)
            if not rc.is_active or rc.revoked_at is not None:
                raise ValueError("Код не активен или отозван")
            if rc.expires_at is not None and rc.expires_at <= now:
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

                region = await db.get(Region, selected_region_id)
                if not region:
                    raise ValueError("Область не найдена")

                user_region_id = selected_region_id

            elif target_role == UserRole.DISTRICT_ADMIN:

                if rc.district_id is None:
                    raise ValueError("Код повреждён: нет district_id")

                d = await db.get(District, rc.district_id)

                if not d:
                    raise ValueError("Район по коду не найден")

                # ✅ users single-scope: только district_id

                user_region_id = None

                user_district_id = d.id

                user_school_id = None

            elif target_role == UserRole.SCHOOL_ADMIN:

                if rc.school_id is None:
                    raise ValueError("Код повреждён: нет school_id")

                s = await db.get(School, rc.school_id)

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
                username=username_norm,
                full_name=full_name.strip() if full_name else None,
                iin=iin.strip() if iin else None,
                password_hash=hash_password(password),
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
            rc.quota_left -= 1
            if rc.quota_left <= 0:
                rc.is_active = False  # удобно, чтобы сразу “не работал”

            use = RegistrationCodeUse(
                code_id=rc.id,
                used_by_user_id=user.id,
                used_at=now,
            )
            await RegistrationCodeRepo.add_use(db, use)

            # commit сделает контекстный менеджер db.begin()
        #import logging
        #log = logging.getLogger(__name__)
        #log.info("REGISTER_BY_CODE role=%s code=%s", target_role, code)
        return user
