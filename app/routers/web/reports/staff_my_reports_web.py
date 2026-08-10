# app/routers/web/reports/staff_my_reports_web.py

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.modules.reports.services.staff_my_reports_service import (
    StaffMyReportsService,
)
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.jinja_filters import MONTH_NAMES_KZ
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/staff/reports",
    tags=["staff-my-reports"],
)


def _current_month() -> int:
    return date.today().month


def _url_with_query(
        base_url: str,
        **params: object,
) -> str:
    """
    Добавить непустые query-параметры к URL.
    """

    query_params = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }

    if not query_params:
        return base_url

    return f"{base_url}?{urlencode(query_params)}"


@router.get(
    "/my",
    name="staff_my_reports_page",
    response_class=HTMLResponse,
)
async def staff_my_reports_page(
        request: Request,

        month: int | None = Query(
            default=None,
            ge=1,
            le=12,
        ),

        task_id: int | None = Query(
            default=None,
            gt=0,
        ),

        db: AsyncSession = Depends(get_db),

        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Быстрый вход сотрудника в назначенные ему отчеты.

    Сценарий:

    1. Без task_id:
       показывает задачи выбранного месяца,
       где сотруднику назначен хотя бы один отчет.

    2. С task_id:
       проверяет назначение сотрудника на отчет задачи
       и сразу переводит на страницу подготовки отчетов:

           /staff/reports/{month_item_id}/templates
    """

    target_month = (
        month
        if month is not None
        else _current_month()
    )

    # =========================================================
    # SELECTED TASK -> REPORTS PAGE
    # =========================================================

    if task_id is not None:
        try:
            await StaffMyReportsService.ensure_task_access(
                db,
                user=user,
                month_item_id=task_id,
            )

        except ValueError as exc:
            page_data = await StaffMyReportsService.get_page(
                db,
                user=user,
                month=target_month,
            )

            return render(
                templates,
                request,
                "staff/reports/staff_my_reports.html",
                {
                    "user": user,
                    "page_data": page_data,

                    "tasks": page_data.tasks,
                    "month": target_month,

                    "MONTH_NAMES": MONTH_NAMES_KZ,

                    "error": str(exc),
                },
                status_code=status.HTTP_403_FORBIDDEN,
            )

        templates_page_url = str(
            request.url_for(
                "staff_report_templates_page",
                month_item_id=task_id,
            )
        )

        return RedirectResponse(
            url=_url_with_query(
                templates_page_url,
                month=target_month,
            ),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # =========================================================
    # TASK SELECTION PAGE
    # =========================================================

    try:
        page_data = await StaffMyReportsService.get_page(
            db,
            user=user,
            month=target_month,
        )

    except ValueError as exc:
        return render(
            templates,
            request,
            "staff/reports/staff_my_reports.html",
            {
                "user": user,
                "page_data": None,

                "tasks": [],
                "month": target_month,

                "MONTH_NAMES": MONTH_NAMES_KZ,

                "error": str(exc),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    return render(
        templates,
        request,
        "staff/reports/staff_my_reports.html",
        {
            "user": user,
            "page_data": page_data,

            "tasks": page_data.tasks,
            "month": target_month,

            "MONTH_NAMES": MONTH_NAMES_KZ,

            "error": None,
        },
    )
