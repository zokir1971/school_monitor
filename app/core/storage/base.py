# app/core/storage/base.py (Универсальный FileStorage (готов к S3/MinIO))

from abc import ABC, abstractmethod


class BaseStorage(ABC):

    @abstractmethod
    def save(self, content: bytes, filename: str) -> tuple[str, str]:
        pass

    @abstractmethod
    def delete(self, path: str) -> None:
        pass
