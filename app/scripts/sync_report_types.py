# app/scripts/sync_report_types.py (Этот скрипт надо запустить на сервере важно!!!)

"""
1. Как запускать локально

Из корня проекта:

python -m app.scripts.sync_report_types
2. Как запускать на сервере

После git pull и перед перезапуском сервиса:

cd /root/school_monitor
source venv/bin/activate
python -m app.scripts.sync_report_types

Потом:

sudo systemctl restart school_monitor
3. Что это дает

Теперь:

если добавить новый ReportType в enum, он сам добавится в report_types
если изменить label_kz, обновится name_kz
если тип исчез из enum, можно не удалять его из БД, а просто оставить как есть
не надо делать миграцию каждый раз из-за справочника
"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.modules.reports.report_type_sync import ReportTypeSyncService
from app.core.logging_config import setup_logging


async def main() -> None:
    setup_logging(debug=True)
    logger = logging.getLogger(__name__)

    async with async_session_maker() as db:  # type: AsyncSession
        result = await ReportTypeSyncService.sync_report_types(
            db,
            deactivate_missing=False,
            commit=True,
        )
        logger.info("Sync result: %s", result)


if __name__ == "__main__":
    asyncio.run(main())
