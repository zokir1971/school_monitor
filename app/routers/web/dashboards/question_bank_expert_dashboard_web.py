# app/routers/web/dashboards/question_bank_expert_dashboard_web.py

from __future__ import annotations

from app.core.feature_access import require_assessment_enabled
from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from fastapi.responses import HTMLResponse

from app.modules.users.deps import (
    require_question_bank_expert, resolve_workspace_context,
)
from app.modules.users.models import User
from app.modules.users.schemas import UserWorkspaceContextDTO
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates


router = APIRouter(dependencies=[Depends(require_assessment_enabled)],
    prefix="/assessment/question-bank/expert",
    tags=["question-bank-expert-dashboard"],
)


@router.get(
    "",
    name="question_bank_expert_dashboard",
    response_class=HTMLResponse,
)
async def question_bank_expert_dashboard(
    request: Request,
    user: User = Depends(
        require_question_bank_expert
    ),
    _workspace_context: UserWorkspaceContextDTO = Depends(
        resolve_workspace_context
    ),
):
    return render(
        templates,
        request,
        "dashboards/question_bank_expert.html",
        {
            "user": user,
        },
    )

'''
@router.get(
    "",
    name="question_bank_expert_dashboard",
    response_class=HTMLResponse,
)
async def question_bank_expert_dashboard(
    request: Request,
    user: User = Depends(
        require_question_bank_expert
    ),
):
    """
    Рабочая панель предметного эксперта Question Bank.

    Доступ определяется активным назначением
    QuestionBankExpert.

    Глобальная UserRole пользователя значения
    для экспертного доступа не имеет.
    """

    return render(
        templates,
        request,
        "dashboards/question_bank_expert.html",
        {
            "user": user,
        },
    )
'''