from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.modules.users.schemas import StaffRegisterDTO, StaffLoginDTO
from app.modules.staff.models_staff_school import SchoolStaffMember
from app.modules.users.models import User, UserRole


class StaffRegistrationError(Exception):
    pass


@dataclass
class StaffRegistrationResult:
    user: User
    staff_member: SchoolStaffMember


class StaffLoginError(Exception):
    pass


@dataclass
class StaffRegistrationResult:
    user: User
    staff_member: SchoolStaffMember


@dataclass
class StaffLoginResult:
    user: User
    staff_member: SchoolStaffMember | None


class StaffAuthService:
    @staticmethod
    async def register_staff_user(
            db: AsyncSession,
            *,
            dto: StaffRegisterDTO,
    ) -> StaffRegistrationResult:
        iin = (dto.iin or "").strip()
        username = (dto.username or "").strip()
        email = (dto.email or "").strip() or None
        phone = (dto.phone or "").strip() or None
        password = dto.password or ""
        password2 = dto.password2 or ""

        if not iin:
            raise StaffRegistrationError("ИИН обязателен")

        if not iin.isdigit() or len(iin) != 12:
            raise StaffRegistrationError("ИИН должен состоять из 12 цифр")

        if not username:
            raise StaffRegistrationError("Логин обязателен")

        if len(username) < 3:
            raise StaffRegistrationError("Логин должен быть не короче 3 символов")

        if not password:
            raise StaffRegistrationError("Пароль обязателен")

        if len(password) < 8:
            raise StaffRegistrationError("Пароль должен быть не короче 8 символов")

        if password != password2:
            raise StaffRegistrationError("Пароли не совпадают")

        staff_member = await db.scalar(
            select(SchoolStaffMember).where(SchoolStaffMember.iin == iin)
        )
        if not staff_member:
            raise StaffRegistrationError("Сотрудник с таким ИИН не найден")

        if hasattr(staff_member, "is_active") and not staff_member.is_active:
            raise StaffRegistrationError("Сотрудник неактивен")

        conditions = [
            User.iin == iin,
            User.username == username,
            User.staff_member_id == staff_member.id,
        ]
        if email:
            conditions.append(User.email == email)
        if phone:
            conditions.append(User.phone == phone)

        existing_user = await db.scalar(
            select(User).where(or_(*conditions))
        )
        if existing_user:
            if existing_user.iin == iin:
                raise StaffRegistrationError("Пользователь с таким ИИН уже зарегистрирован")
            if existing_user.username == username:
                raise StaffRegistrationError("Логин уже занят")
            if existing_user.staff_member_id == staff_member.id:
                raise StaffRegistrationError("Для этого сотрудника аккаунт уже создан")
            if email and existing_user.email == email:
                raise StaffRegistrationError("Email уже используется")
            if phone and existing_user.phone == phone:
                raise StaffRegistrationError("Телефон уже используется")
            raise StaffRegistrationError("Пользователь уже существует")

        user = User(
            username=username,
            iin=iin,
            full_name=staff_member.full_name,
            password_hash=hash_password(password),
            role=UserRole.SCHOOL_STAFF,
            is_active=True,
            email=email,
            phone=phone,
            school_id=staff_member.school_id,
            staff_member_id=staff_member.id,
        )

        db.add(user)
        await db.flush()
        await db.commit()
        await db.refresh(user)

        return StaffRegistrationResult(
            user=user,
            staff_member=staff_member,
        )

    @staticmethod
    async def login_staff_user(
            db: AsyncSession,
            *,
            dto: StaffLoginDTO,
    ) -> StaffLoginResult:
        identifier = (dto.identifier or "").strip()
        password = dto.password or ""

        if not identifier:
            raise StaffLoginError("Введите ИИН или логин")

        if not password:
            raise StaffLoginError("Введите пароль")

        user = await db.scalar(
            select(User).where(
                or_(
                    User.username == identifier,
                    User.iin == identifier,
                )
            )
        )
        if not user:
            raise StaffLoginError("Пользователь не найден")

        if not user.is_active:
            raise StaffLoginError("Аккаунт отключен")

        if user.role != UserRole.SCHOOL_STAFF:
            raise StaffLoginError("Вход для этой роли через эту форму недоступен")

        if not verify_password(password, user.password_hash):
            raise StaffLoginError("Неверный пароль")

        staff_member = None
        if user.staff_member_id:
            staff_member = await db.scalar(
                select(SchoolStaffMember).where(
                    SchoolStaffMember.id == user.staff_member_id
                )
            )

        user.last_login_at = __import__("datetime").datetime.utcnow()
        await db.commit()

        return StaffLoginResult(
            user=user,
            staff_member=staff_member,
        )
