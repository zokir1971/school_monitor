# app/modules/assessment/schemas/question_bank_review_dto.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.modules.assessment.enums import (
    QuestionBankItemStatus,
    QuestionBankReviewDecision,
)


# =========================================================
# CREATE REVIEW
# =========================================================


@dataclass(slots=True, frozen=True)
class QuestionBankReviewCreateInput:
    """
    Данные экспертного решения.

    reviewer_user_id не принимается от клиента.
    Эксперт определяется сервером по текущему
    авторизованному пользователю.
    """

    decision: QuestionBankReviewDecision
    comment: str | None = None


@dataclass(slots=True, frozen=True)
class QuestionBankReviewCreateResult:
    """
    Результат сохранения экспертного решения
    и изменения lifecycle QuestionBankItem.
    """

    review_id: int
    question_bank_item_id: int

    decision: QuestionBankReviewDecision
    item_status: QuestionBankItemStatus


# =========================================================
# REVIEW HISTORY
# =========================================================


@dataclass(slots=True, frozen=True)
class QuestionBankReviewHistoryItemDTO:
    """
    Одна историческая запись экспертной проверки.
    """

    review_id: int

    reviewer_user_id: int | None
    reviewer_name: str | None

    decision: QuestionBankReviewDecision
    comment: str | None

    created_at: datetime
