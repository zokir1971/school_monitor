# app/core/storage/enums.py (Категории документов)

from enum import Enum


class StorageCategory(str, Enum):
    """
    Типы документов в файловом хранилище.
    """

    TASK_REPORT = "task-reports"
    FINAL_DOCUMENT = "final-documents"
    REVIEW_PROTOCOL = "review-protocols"
