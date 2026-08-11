# app/core/config.py
from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class StorageBackend(str, Enum):
    LOCAL = "local"
    S3 = "s3"


class Settings(BaseSettings):
    # ---------------------------------------------------------
    # Основные настройки приложения
    # ---------------------------------------------------------

    DATABASE_URL: str

    APP_ENV: str = "dev"
    DEBUG: bool = False

    SECRET_KEY: str

    # URL платформы для ссылок в сообщениях
    PLATFORM_URL: str = "http://91.243.71.245"

    # Секрет для хеширования регистрационных кодов
    CODE_PEPPER: str

    # ---------------------------------------------------------
    # Файловое хранилище
    # ---------------------------------------------------------

    STORAGE_BACKEND: StorageBackend = StorageBackend.LOCAL

    # Локальное хранилище
    STORAGE_LOCAL_ROOT: Path = Path("storage")
    STORAGE_PUBLIC_BASE_URL: str = "/storage"

    # ---------------------------------------------------------
    # S3 / MinIO
    # ---------------------------------------------------------

    # Для MinIO:
    # http://127.0.0.1:9000
    #
    # Для AWS S3:
    # переменную можно не задавать
    S3_ENDPOINT_URL: str | None = None

    # Публичный endpoint для presigned URL.
    # Для MinIO обычно отличается от внутреннего endpoint:
    # S3_ENDPOINT_URL=http://127.0.0.1:9000
    # S3_PUBLIC_ENDPOINT_URL=http://<public-host>:9000
    # Для AWS S3 можно не задавать.
    S3_PUBLIC_ENDPOINT_URL: str | None = None

    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None

    S3_REGION: str = "us-east-1"
    S3_BUCKET: str = "school-monitor-documents"

    S3_VERIFY_SSL: bool = True
    S3_CREATE_BUCKET_ON_STARTUP: bool = False

    S3_PRESIGNED_URL_EXPIRES_IN: int = Field(
        default=300,
        ge=60,
        le=86_400,
    )

    # ---------------------------------------------------------
    # Ограничения файлов
    # ---------------------------------------------------------

    MAX_UPLOAD_FILE_SIZE_MB: int = Field(
        default=20,
        gt=0,
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def is_debug(self) -> bool:
        return (
            self.DEBUG
            or self.APP_ENV.strip().lower()
            in {
                "dev",
                "local",
                "development",
            }
        )

    @property
    def use_s3(self) -> bool:
        return (
            self.STORAGE_BACKEND
            is StorageBackend.S3
        )

    @property
    def use_local_storage(self) -> bool:
        return (
            self.STORAGE_BACKEND
            is StorageBackend.LOCAL
        )

    @property
    def max_upload_file_size_bytes(self) -> int:
        return (
            self.MAX_UPLOAD_FILE_SIZE_MB
            * 1024
            * 1024
        )

    @property
    def storage_public_base_url(self) -> str:
        """
        Нормализованный публичный URL локального хранилища.
        """

        normalized_url = (
            self.STORAGE_PUBLIC_BASE_URL
            .strip()
        )

        if not normalized_url:
            return "/storage"

        if not normalized_url.startswith("/"):
            normalized_url = (
                f"/{normalized_url}"
            )

        return normalized_url.rstrip("/")

    @property
    def s3_endpoint_url(self) -> str | None:
        """
        Нормализованный endpoint MinIO/S3.

        Для AWS S3 возвращает None.
        """

        if self.S3_ENDPOINT_URL is None:
            return None

        normalized_url = (
            self.S3_ENDPOINT_URL
            .strip()
            .rstrip("/")
        )

        return normalized_url or None

    @property
    def s3_public_endpoint_url(self) -> str | None:
        """
        Публичный endpoint для формирования presigned URL.

        Если отдельный публичный endpoint не задан,
        используется основной S3 endpoint.
        """

        if self.S3_PUBLIC_ENDPOINT_URL is None:
            return self.s3_endpoint_url

        normalized_url = (
            self.S3_PUBLIC_ENDPOINT_URL
            .strip()
            .rstrip("/")
        )

        return normalized_url or self.s3_endpoint_url

    @property
    def s3_bucket(self) -> str:
        return self.S3_BUCKET.strip().lower()

    def validate_storage_configuration(
        self,
    ) -> None:
        """
        Проверяет конфигурацию выбранного хранилища.
        """

        if self.use_local_storage:
            if not str(
                self.STORAGE_LOCAL_ROOT
            ).strip():
                raise RuntimeError(
                    "Для локального хранилища необходимо "
                    "указать STORAGE_LOCAL_ROOT."
                )

            return

        missing_settings: list[str] = []

        if not self.S3_ACCESS_KEY:
            missing_settings.append(
                "S3_ACCESS_KEY"
            )

        if not self.S3_SECRET_KEY:
            missing_settings.append(
                "S3_SECRET_KEY"
            )

        if not self.s3_bucket:
            missing_settings.append(
                "S3_BUCKET"
            )

        if missing_settings:
            raise RuntimeError(
                "Для S3-хранилища не заполнены "
                "обязательные настройки: "
                + ", ".join(missing_settings)
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]

    settings.validate_storage_configuration()

    return settings
