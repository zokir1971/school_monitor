from __future__ import annotations
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.org.models import School


class SchoolScopeRepo:
    """School metadata and transaction lock for school-scoped operations."""

    @staticmethod
    async def get_name(db: AsyncSession, *, school_id: int) -> str | None:
        return await db.scalar(select(School.name).where(School.id == school_id))

    @staticmethod
    async def lock_import(db: AsyncSession, *, school_id: int) -> None:
        await db.execute(
            text("SELECT pg_advisory_xact_lock(731209, :school)"),
            {"school": school_id},
        )
