# app/core/storage/local.py (Локальное хранилище для файлов загрузки)

from pathlib import Path
from uuid import uuid4

from app.core.storage.base import BaseStorage


class LocalStorage(BaseStorage):
    ROOT = Path("storage")

    def save(self, content: bytes, filename: str):
        ext = Path(filename).suffix
        stored_name = f"{uuid4().hex}{ext}"

        relative_path = Path("uploads/task_documents") / stored_name
        abs_path = self.ROOT / relative_path

        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(content)

        return str(relative_path), stored_name

    def delete(self, path: str):
        if not path:
            return

        abs_path = self.ROOT / path
        if abs_path.exists():
            abs_path.unlink(missing_ok=True)
