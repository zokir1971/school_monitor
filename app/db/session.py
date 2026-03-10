# app/db/session.py (Подключение к PostgreSQL, создаётся соединение, настраивается пул. Сессия БД async)
# app/db/session.py

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings


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
    pool_size=20,
    max_overflow=40,
    echo=settings.is_debug,  # правильнее чем APP_ENV == "dev"
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

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
