# app/scripts/bootstrap_superuser.py

from __future__ import annotations

import asyncio
import os

from app.core.security import hash_password
from app.db.session import async_session_maker
from app.modules.users.services.bootstrap import BootstrapService


def get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Не задана переменная окружения: {name}")
    return value


async def main() -> None:
    username = get_env("FIRST_SUPERUSER_USERNAME")
    iin = get_env("FIRST_SUPERUSER_IIN")
    full_name = get_env("FIRST_SUPERUSER_FULL_NAME")
    email = get_env("FIRST_SUPERUSER_EMAIL")
    phone = get_env("FIRST_SUPERUSER_PHONE")
    password = get_env("FIRST_SUPERUSER_PASSWORD")

    async with async_session_maker() as db:
        allowed = await BootstrapService.can_bootstrap_superuser(db)
        if not allowed:
            print("Суперадмин уже существует. Создание не требуется.")
            return

        await BootstrapService.create_superuser(
            db,
            username=username,
            full_name=full_name,
            iin=iin,
            email=email,
            phone=phone,
            password_hash=hash_password(password),
        )

        print("Суперадмин успешно создан.")


if __name__ == "__main__":
    asyncio.run(main())
    