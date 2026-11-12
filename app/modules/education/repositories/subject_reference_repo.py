"""Subject SQL operations. Transactions belong to the web caller."""
from __future__ import annotations
from typing import Any, cast
from sqlalchemy import Table, func, inspect, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.education.models import Subject
from app.modules.education.schemas.subject_reference_dto import SubjectReferenceInput, SubjectReferenceRow


def _columns():
    return cast(Table, Subject.__table__).c


def _filters(query: str, state: str, category_id: int | None = None):
    c = _columns()
    filters = []
    if state != 'all':
        filters.append(c.is_active.is_(state == 'active'))
    if category_id is not None:
        filters.append(c.category_id.is_(None) if category_id == 0 else c.category_id == category_id)
    if query:
        # User text is literal, never a wildcard pattern or a SQL expression.
        pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        filters.append(or_(c.code.ilike(pattern, escape='\\'),
                           c.name_kz.ilike(pattern, escape='\\'),
                           c.name_ru.ilike(pattern, escape='\\')))
    return filters


class SubjectReferenceRepo:
    @staticmethod
    async def count(db: AsyncSession, *, query: str, state: str, category_id: int | None = None) -> int:
        return int(await db.scalar(
            select(func.count()).select_from(Subject.__table__).where(*_filters(query, state, category_id))) or 0)

    @staticmethod
    async def list_page(
            db: AsyncSession,
            *, query: str,
            state: str,
            offset: int,
            limit: int, category_id: int | None = None) -> list[SubjectReferenceRow]:
        c = _columns()
        result = await db.execute(select(c.id, c.code, c.name_kz, c.name_ru, c.is_active,
                                         c.sort_order, c.created_at, c.updated_at, c.category_id, c.curriculum_role)
                                  .where(*_filters(query, state, category_id))
                                  .order_by(c.sort_order, c.name_kz, c.id)
                                  .offset(offset).limit(limit))
        return [SubjectReferenceRow(**dict(row)) for row in result.mappings()]

    @staticmethod
    async def get(db: AsyncSession, subject_id: int, *, lock: bool = False) -> SubjectReferenceRow | None:
        c = _columns()
        statement = select(
            c.id, c.code, c.name_kz, c.name_ru, c.is_active, c.sort_order, c.created_at, c.updated_at, c.category_id,
            c.curriculum_role) \
            .where(c.id == subject_id)
        if lock:
            statement = statement.with_for_update()
        result = await db.execute(statement)
        row = result.mappings().one_or_none()
        return SubjectReferenceRow(**dict(row)) if row is not None else None

    @staticmethod
    async def code_exists(db: AsyncSession, code: str) -> bool:
        c = _columns()
        return await db.scalar(select(c.id).where(func.lower(c.code) == code.lower()).limit(1)) is not None

    @staticmethod
    async def create(db: AsyncSession, data: SubjectReferenceInput) -> int:
        subject = Subject(code=data.code, name_kz=data.name_kz, name_ru=data.name_ru,
                          sort_order=data.sort_order, is_active=data.is_active,
                          category_id=data.category_id, curriculum_role=data.curriculum_role)
        db.add(subject)
        await db.flush()
        return subject.id

    @staticmethod
    async def update(db: AsyncSession, subject_id: int, data: SubjectReferenceInput) -> None:
        c = _columns()
        await db.execute(update(cast(Table, Subject.__table__)).where(c.id == subject_id).values(
            name_kz=data.name_kz, name_ru=data.name_ru, sort_order=data.sort_order,
            is_active=data.is_active, category_id=data.category_id,
            curriculum_role=data.curriculum_role, updated_at=func.now()))

    @staticmethod
    async def refresh_user_after_rollback(db: AsyncSession, user: Any) -> None:
        state = inspect(user, raiseerr=False)
        if state is not None and state.session is db.sync_session:
            await db.refresh(user)

    @staticmethod
    def is_code_conflict(error: IntegrityError) -> bool:
        original = error.orig
        cause = getattr(original, '__cause__', None)
        diagnostic = getattr(original, 'diag', None)
        sqlstate = getattr(original, 'sqlstate', None) or getattr(original, 'pgcode', None)
        constraint = (getattr(original, 'constraint_name', None)
                      or getattr(cause, 'constraint_name', None)
                      or getattr(diagnostic, 'constraint_name', None))
        return sqlstate == '23505' and constraint == 'subjects_code_key'
