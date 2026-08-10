# app/utils/storage.py (формирует путь для чтение файла)
from pathlib import Path

from fastapi import HTTPException


BASE_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BASE_DIR / "storage"


def resolve_storage_file(relative_path: str | Path) -> Path:
    """
    Преобразует относительный путь из БД
    в абсолютный путь внутри storage.
    """

    storage_root = STORAGE_DIR.resolve()

    file_path = Path(str(relative_path))

    if not file_path.is_absolute():
        file_path = storage_root / file_path

    file_path = file_path.resolve()

    try:
        file_path.relative_to(storage_root)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Некорректный путь файла",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Файл отсутствует на сервере",
        )

    return file_path
