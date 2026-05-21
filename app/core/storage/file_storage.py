# app/core/storage/file_storage.py (безопасное удаление итоговых документов из ситемы)

from pathlib import Path
from uuid import uuid4


class FileStorage:
    STORAGE_ROOT = Path("")

    @classmethod
    def save_file(cls, content: bytes, original_name: str) -> tuple[str, str]:
        ext = Path(original_name).suffix
        stored_name = f"{uuid4().hex}{ext}"

        relative_path = Path("uploads/task_documents") / stored_name
        absolute_path = cls.STORAGE_ROOT / relative_path

        absolute_path.parent.mkdir(parents=True, exist_ok=True)
        absolute_path.write_bytes(content)

        return str(relative_path), stored_name

    @classmethod
    def delete_file(cls, file_path: str | None):
        if not file_path:
            return

        abs_path = cls.STORAGE_ROOT / file_path
        if abs_path.exists():
            abs_path.unlink(missing_ok=True)
