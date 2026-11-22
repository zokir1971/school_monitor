# app/db/session.py (Подключение к PostgreSQL, создаётся соединение, настраивается пул. Сессия БД async)

from __future__ import annotations

from typing import AsyncGenerator
from fastapi import Request

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
# Регистрируем все модели до использования ORM-сессий.
import app.db.models  # noqa: F401


# ---------------------------------
# Settings
# ---------------------------------

settings = get_settings()


# ---------------------------------
# Engine (asyncpg)
# ---------------------------------

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
    echo=False,
)

# ---------------------------------
# Session factory
# ---------------------------------

async_session_maker = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


# ---------------------------------
# FastAPI dependency
# ---------------------------------

async def get_db(request: Request = None) -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        from app.modules.statistics.activity_tracking import module_for, observe_session
        cleanup = None
        if request is not None and request.method in ('POST', 'PUT', 'PATCH', 'DELETE') and module_for(request.url.path):
            cleanup = observe_session(session.sync_session, request.scope)
        try:
            yield session
        finally:
            if cleanup:
                cleanup()
