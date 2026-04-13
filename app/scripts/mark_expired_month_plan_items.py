# app/scripts/mark_expired_month_plan_items.py (обновляет статус выполнения задач автоматический каждый день)

# Это надо на сервере запустит и добавить в cron и создать папку логов это важно

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

from app.db.session import async_session_maker
from app.modules.staff.service_task import (
    SchoolMonthPlanItemStatusService,
)

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


async def main() -> None:
    async with async_session_maker() as db:
        updated_count = await SchoolMonthPlanItemStatusService.auto_mark_expired_as_not_executed(db)
        print(f"Просроченные задачи обновлены: {updated_count}")


if __name__ == "__main__":
    asyncio.run(main())
