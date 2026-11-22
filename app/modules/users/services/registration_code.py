"""Atomic, scoped L1/L2/L3 issuance. The caller commits the complete batch."""
from __future__ import annotations
from datetime import timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.common.time import utcnow
from app.core.security import registration_code_lookup_hash
from app.modules.org.models import Region, District, School
from app.modules.users.enums import UserRole
from app.modules.users.models import User, RegistrationCode
from app.modules.users.repo import RegistrationCodeRepo
from app.modules.users.validators import _make_human_code

LEVELS = {
    'L1': (UserRole.SUPERUSER, UserRole.REGION_ADMIN, Region, 'region_id', 'region'),
    'L2': (UserRole.REGION_ADMIN, UserRole.DISTRICT_ADMIN, District, 'district_id', 'district'),
    'L3': (UserRole.DISTRICT_ADMIN, UserRole.SCHOOL_ADMIN, School, 'school_id', 'school'),
}
MAX_BATCH_TARGETS = 1000

class RegistrationCodeService:
    @staticmethod
    async def actor(db, *, user_id, level):
        if level not in LEVELS:
            raise ValueError('Некорректный уровень кода')
        U = User.__table__
        user = (await db.execute(select(U.c.id, U.c.role, U.c.region_id, U.c.district_id, U.c.is_active)
                .where(U.c.id == user_id))).mappings().one_or_none()
        if not user or not user['is_active'] or user['role'] != LEVELS[level][0]:
            raise HTTPException(403, 'Нет права выдавать коды этого уровня')
        if level == 'L2' and user['region_id'] is None:
            raise HTTPException(403, 'У пользователя не задан region_id')
        if level == 'L3' and user['district_id'] is None:
            raise HTTPException(403, 'У пользователя не задан district_id')
        return user

    @staticmethod
    def target_query(*, actor, level):
        table = LEVELS[level][2].__table__
        statement = select(table.c.id, table.c.name)
        if level == 'L2': statement = statement.where(table.c.region_id == actor['region_id'])
        if level == 'L3': statement = statement.where(table.c.district_id == actor['district_id'])
        return statement

    @staticmethod
    async def scope_name(db, *, actor, level):
        if level == 'L1': return None
        table = (Region if level == 'L2' else District).__table__
        key = actor['region_id'] if level == 'L2' else actor['district_id']
        row = (await db.execute(select(table.c.id, table.c.name).where(table.c.id == key))).mappings().one_or_none()
        if row is None: raise HTTPException(403, 'Территория пользователя не найдена')
        return row

    @classmethod
    async def get_catalog(cls, db, *, user_id, level):
        actor = await cls.actor(db, user_id=user_id, level=level)
        scope = await cls.scope_name(db, actor=actor, level=level)
        table = LEVELS[level][2].__table__
        rows = (await db.execute(cls.target_query(actor=actor, level=level).order_by(table.c.name, table.c.id))).mappings().all()
        return scope, rows

    @classmethod
    async def issue_batch(cls, db, *, issued_by_user_id, level, target_ids, quota_total=1, expires_days=30):
        if type(quota_total) is not int or not 1 <= quota_total <= 2147483647:
            raise ValueError('Квота должна быть положительным целым числом')
        if expires_days is not None and (type(expires_days) is not int or not 1 <= expires_days <= 36500):
            raise ValueError('Некорректный срок действия кода')
        if not target_ids or len(target_ids) > MAX_BATCH_TARGETS:
            raise ValueError('Выберите от 1 до 1000 организаций')
        if any(type(key) is not int or key <= 0 for key in target_ids):
            raise ValueError('Некорректная организация')
        ids = sorted(set(target_ids))
        actor = await cls.actor(db, user_id=issued_by_user_id, level=level)
        _, target_role, model, scope_column, name_prefix = LEVELS[level]
        table = model.__table__
        # Lock actual target rows, even when there are no previous codes yet.
        # Every batch uses the same id order to avoid reversed batch lock order.
        rows = (await db.execute(cls.target_query(actor=actor, level=level)
                .where(table.c.id.in_(ids)).order_by(table.c.id).with_for_update())).mappings().all()
        if len(rows) != len(ids):
            raise ValueError('Выбрана чужая или несуществующая организация')
        C = RegistrationCode.__table__
        previous = (await db.execute(select(C).where(C.c.target_role == target_role,
                C.c[scope_column].in_(ids), C.c.is_active.is_(True), C.c.revoked_at.is_(None))
                .order_by(C.c.id).with_for_update())).mappings().all()
        now = utcnow()
        for row in previous:
            expires = row['expires_at']
            if expires is not None and expires.tzinfo is None:
                expires = expires.replace(tzinfo=now.tzinfo)
            if (expires is None or expires > now) and 0 < row['quota_left'] < row['quota_total']:
                raise ValueError('По выбранной организации код уже частично использован. Перевыпуск запрещён.')
        # No mutations until the full selection and all existing codes are valid.
        generated = []
        unique = set()
        for row in rows:
            for attempt in range(20):
                raw = _make_human_code(prefix=level, group_len=8)
                lookup = registration_code_lookup_hash(raw)
                if lookup not in unique:
                    unique.add(lookup); generated.append((row, raw, lookup)); break
            else: raise ValueError('Не удалось сформировать уникальные коды. Повторите выдачу.')
        existing = set((await db.execute(select(C.c.code_lookup_hash).where(C.c.code_lookup_hash.in_(unique)))).scalars())
        if existing:
            raise ValueError('Совпадение кодов. Повторите выдачу.')
        if previous:
            await db.execute(update(C).where(C.c.id.in_([row['id'] for row in previous]))
                    .values(is_active=False, revoked_at=now, revoked_by_user_id=issued_by_user_id))
        expires_at = now + timedelta(days=expires_days) if expires_days is not None else None
        result = []
        for row, raw, lookup in generated:
            obj = RegistrationCode(code_lookup_hash=lookup, target_role=target_role,
                region_id=row['id'] if level == 'L1' else None,
                district_id=row['id'] if level == 'L2' else None,
                school_id=row['id'] if level == 'L3' else None,
                issued_by_user_id=issued_by_user_id, issued_at=now,
                quota_total=quota_total, quota_left=quota_total, is_active=True, expires_at=expires_at)
            db.add(obj);result.append((raw, obj, row['name']))
        await db.flush()
        return result

    @classmethod
    async def issue_l1_code(cls, db, *, issued_by_user_id, region_id, quota_total=1, expires_days=30):
        raw, obj, _ = (await cls.issue_batch(db, issued_by_user_id=issued_by_user_id, level='L1',
            target_ids=[region_id], quota_total=quota_total, expires_days=expires_days))[0]
        return raw, obj

    @classmethod
    async def issue_l2_code(cls, db, *, issued_by_user_id, region_id, district_id, quota_total=1, expires_days=30):
        actor = await cls.actor(db, user_id=issued_by_user_id, level='L2')
        if region_id != actor['region_id']: raise HTTPException(403, 'Чужая область')
        raw, obj, _ = (await cls.issue_batch(db, issued_by_user_id=issued_by_user_id, level='L2',
            target_ids=[district_id], quota_total=quota_total, expires_days=expires_days))[0]
        return raw, obj

    @classmethod
    async def issue_l3_code(cls, db, *, issued_by_user_id, school_id, quota_total=1, expires_days=30):
        raw, obj, _ = (await cls.issue_batch(db, issued_by_user_id=issued_by_user_id, level='L3',
            target_ids=[school_id], quota_total=quota_total, expires_days=expires_days))[0]
        return raw, obj

    @staticmethod
    async def preview_code(db: AsyncSession, *, invite_code: str) -> RegistrationCode:
        lookup = registration_code_lookup_hash(invite_code.strip().upper())
        obj = await RegistrationCodeRepo.get_by_lookup_hash(db, lookup)
        if not obj: raise ValueError('Код не найден')
        if not obj.is_active or obj.revoked_at is not None: raise ValueError('Код отключён')
        now = utcnow();expires = obj.expires_at
        if expires is not None and expires.tzinfo is None: expires = expires.replace(tzinfo=now.tzinfo)
        if expires is not None and expires <= now: raise ValueError('Срок действия кода истёк')
        if obj.quota_left <= 0: raise ValueError('Лимит регистраций по коду исчерпан')
        return obj
