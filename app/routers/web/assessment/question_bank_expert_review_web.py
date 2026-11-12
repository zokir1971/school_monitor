# app/routers/web/assessment/question_bank_expert_review_web.py

from __future__ import annotations

from typing import cast

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.assessment.services.bilingual_question_views import review_variants
from app.modules.assessment.services.question_bank_expert_service import (
    QuestionBankExpertService,
)
from app.modules.users.deps import require_question_bank_expert
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/assessment/question-bank/expert/review",
    tags=["question-bank-expert-review"],
)


# =========================================================
# HELPERS
# =========================================================


def _get_user_id(
    user: User,
) -> int:
    """
    Возвращает идентификатор текущего пользователя.

    Отдельный helper нужен для корректной типизации
    SQLAlchemy mapped attribute.
    """

    return cast(
        int,
        user.id,
    )


# =========================================================
# REVIEW QUEUE
# =========================================================


@router.get(
    "",
    name="question_bank_expert_review_page",
    response_class=HTMLResponse,
)
async def question_bank_expert_review_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_question_bank_expert),
):
    """
    Очередь Human Review предметного эксперта.

    Эксперт видит REVIEW-задания:

        - только по предметам своего активного
          QuestionBankExpert scope;

        - только задания других пользователей.

    Просмотр очереди не изменяет lifecycle задания.
    """

    user_id = _get_user_id(user)

    try:
        page = (
            await QuestionBankExpertService
            .get_review_page(
                db,
                user_id=user_id,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return render(
        templates,
        request,
        "teacher/assessment/question_bank/review.html",
        {
            "user": user,
            "page": page,
            "bilingual_variants": await review_variants(db, page.items),
        },
    )


# =========================================================
# APPROVE
# =========================================================


@router.post(
    "/{item_id}/approve",
    name="question_bank_expert_review_approve",
)
async def question_bank_expert_review_approve(
    request: Request,
    item_id: int,
    comment: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_question_bank_expert),
):
    """
    Одобряет REVIEW-задание предметным экспертом.

    Lifecycle:

        REVIEW -> READY
    """

    reviewer_user_id = _get_user_id(user)

    try:
        await QuestionBankExpertService.approve_review(
            db,
            item_id=item_id,
            reviewer_user_id=reviewer_user_id,
            comment=comment,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=request.url_for(
            "question_bank_expert_review_page"
        ),
        status_code=303,
    )


# =========================================================
# REJECT
# =========================================================


@router.post(
    "/{item_id}/reject",
    name="question_bank_expert_review_reject",
)
async def question_bank_expert_review_reject(
    request: Request,
    item_id: int,
    comment: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_question_bank_expert),
):
    """
    Отклоняет REVIEW-задание предметным экспертом.

    Lifecycle:

        REVIEW -> REJECTED
    """

    reviewer_user_id = _get_user_id(user)

    try:
        await QuestionBankExpertService.reject_review(
            db,
            item_id=item_id,
            reviewer_user_id=reviewer_user_id,
            comment=comment,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=request.url_for(
            "question_bank_expert_review_page"
        ),
        status_code=303,
    )
