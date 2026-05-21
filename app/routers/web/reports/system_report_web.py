# app/routers/web/reports/system_report_web.py

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.reports.template_registry import SYSTEM_REPORT_CONFIG
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/staff/reports",
    tags=["staff-system-reports"],
)


def _page_data_to_context(page_data) -> dict:
    return {
        "document": getattr(page_data, "document", None),
        "selected_report": getattr(page_data, "selected_report", None),

        "lesson_report": getattr(page_data, "lesson_report", None),
        "checking_notebooks_report": getattr(page_data, "report", None),

        "template": getattr(page_data, "template", None),
        "schema": getattr(page_data, "schema", {}),

        "criteria": getattr(page_data, "criteria", []),
        "score_scale": getattr(page_data, "score_scale", []),

        "criteria_scores": getattr(page_data, "criteria_scores", {}),
        "saved_info": getattr(page_data, "saved_info", {}),
        "scores": getattr(page_data, "scores", {}),
        "col_sums": getattr(page_data, "col_sums", {}),

        "rows": getattr(page_data, "rows", []),

        "total_score": getattr(page_data, "total_score", 0),
        "max_score": getattr(page_data, "max_score", 0),
        "percent": getattr(page_data, "percent", 0),
        "level": getattr(page_data, "level", None),

        "report": getattr(page_data, "report", None),
        "readonly": getattr(page_data, "readonly", False),
        "is_completed": getattr(page_data, "is_completed", False),

        "teacher_name": getattr(page_data, "teacher_name", ""),
        "teacher_position": getattr(page_data, "teacher_position", ""),
        "teacher_category": getattr(page_data, "teacher_category", ""),
        "subject": getattr(page_data, "subject", ""),

        "observer_name": getattr(page_data, "observer_name", ""),
        "observer_position": getattr(page_data, "observer_position", ""),

        "school_name": getattr(page_data, "school_name", ""),

        "class_name": getattr(page_data, "class_name", ""),
        "group_name": getattr(page_data, "group_name", ""),
        "lesson_datetime": getattr(page_data, "lesson_datetime", ""),

        "theme": getattr(page_data, "theme", ""),
        "learning_objectives": getattr(page_data, "learning_objectives", ""),
        "lesson_objectives_1": getattr(page_data, "lesson_objectives_1", ""),
        "lesson_objectives_2": getattr(page_data, "lesson_objectives_2", ""),
        "lesson_objectives_3": getattr(page_data, "lesson_objectives_3", ""),

        "feedback": getattr(page_data, "feedback", ""),
        "suggestion_control": getattr(page_data, "suggestion_control", ""),
    }


def _redirect_url(
    request: Request,
    *,
    month_item_id: int,
    selected_report_id: int,
    report_code: str,
    success: str | None = None,
    error: str | None = None,
) -> str:
    base_url = str(
        request.url_for(
            "staff_system_report_fill_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )
    )

    url = f"{base_url}?report_code={quote(str(report_code))}"

    if success:
        url += f"&success={quote(success)}"

    if error:
        url += f"&error={quote(error)}"

    return url


@router.get(
    "/{month_item_id}/templates/{selected_report_id}/system-fill",
    name="staff_system_report_fill_page",
    response_class=HTMLResponse,
)
async def staff_system_report_fill_page(
    request: Request,
    month_item_id: int,
    selected_report_id: int,
    report_code: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_roles(
            UserRole.SCHOOL_STAFF,
            UserRole.SCHOOL_ADMIN,
        )
    ),
):
    config = SYSTEM_REPORT_CONFIG.get(report_code)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Системный шаблон не настроен",
        )

    service = config["service"]
    template_name = config["template"]

    try:
        page_data = await service.get_fill_page_data(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    context = {
        "request": request,
        "user": user,

        "month_item_id": month_item_id,
        "selected_report_id": selected_report_id,
        "report_code": report_code,

        "page_data": page_data,

        "error": request.query_params.get("error"),
        "success": request.query_params.get("success"),
    }

    context.update(_page_data_to_context(page_data))

    return templates.TemplateResponse(
        template_name,
        context,
    )


@router.post(
    "/{month_item_id}/templates/{selected_report_id}/system-fill",
    name="staff_system_report_fill_post",
)
async def staff_system_report_fill_post(
    request: Request,
    month_item_id: int,
    selected_report_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_roles(
            UserRole.SCHOOL_STAFF,
            UserRole.SCHOOL_ADMIN,
        )
    ),
):
    form = await request.form()
    form_data = dict(form)

    report_code = form_data.get("report_code")

    if not report_code:
        return RedirectResponse(
            url=_redirect_url(
                request,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                report_code="",
                error="Не указан тип системного отчета.",
            ),
            status_code=303,
        )

    config = SYSTEM_REPORT_CONFIG.get(report_code)

    if not config:
        raise HTTPException(
            status_code=404,
            detail="Системный шаблон не настроен",
        )

    service = config["service"]
    action = form_data.get("action")

    try:
        if hasattr(service, "save_or_complete"):
            await service.save_or_complete(
                db,
                request=request,
                form=form,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                user=user,
                templates=templates,
            )
        else:
            await service.save_lesson_observation(
                db,
                request=request,
                templates=templates,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                user=user,
                form_data=form_data,
            )

        success = (
            "Отчет сохранен и подписан."
            if action == "complete"
            else "Черновик сохранен."
        )

        return RedirectResponse(
            url=_redirect_url(
                request,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                report_code=report_code,
                success=success,
            ),
            status_code=303,
        )

    except ValueError as exc:
        await db.rollback()

        return RedirectResponse(
            url=_redirect_url(
                request,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                report_code=report_code,
                error=str(exc),
            ),
            status_code=303,
        )

    except SQLAlchemyError:
        await db.rollback()

        return RedirectResponse(
            url=_redirect_url(
                request,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                report_code=report_code,
                error="Ошибка при сохранении данных.",
            ),
            status_code=303,
        )
