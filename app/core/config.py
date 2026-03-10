# app/core/config.py (инициализация проекта)

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    APP_ENV: str = "dev"
    SECRET_KEY: str
    DEBUG: bool = False

    # секрет для хэша регистрационных кодов
    CODE_PEPPER: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # не падать если есть лишние переменные
    )

    @property
    def is_debug(self) -> bool:
        return self.DEBUG or self.APP_ENV.lower() in {
            "dev", "local", "development"
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
