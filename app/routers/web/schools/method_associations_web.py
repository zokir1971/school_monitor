# app/routers/web/schools/method_associations_web.py

from dataclasses import asdict
from typing import cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db
from app.modules.schools.method_association_service import (
    SchoolMethodAssociationService,
    MethodAssociationSettingsConflict,
    MethodAssociationDataConflict,
)
from app.modules.users.deps import require_school_admin_scope
from app.modules.users.models import User
from app.routers.web.helpers.render import render, render_error, _normalize_user
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/school-admin",
    tags=["School method associations"],
)

ERROR_MESSAGES = {
    "school_not_found": (
        "Не удалось определить школу текущего пользователя."
    ),
    "invalid_codes": (
        "Передан недопустимый список методических объединений."
    ),
}


def get_error_message(request: Request) -> str | None:
    """
    Преобразует код ошибки из query-параметра
    в понятное сообщение.
    """

    error_code = request.query_params.get("error")

    if not error_code:
        return None

    return ERROR_MESSAGES.get(
        error_code,
        "Не удалось выполнить операцию.",
    )


@router.get(
    "/method-associations",
    name="school_method_association_settings_page",
    response_class=HTMLResponse,
)
async def school_method_association_settings_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_school_admin_scope),
):
    """
    Страница настройки методических объединений школы.
    """

    school_id = cast(
        int | None,
        getattr(user, "school_id", None),
    )

    if school_id is None:
        return render_error(
            templates,
            request,
            "school_admin/method_associations.html",
            {
                "user": user,
                "school_id": None,
                "options": [],
                "success": False,
            },
            error=(
                "Не удалось определить школу "
                "текущего пользователя."
            ),
            status_code=400,
        )

    page_data = (
        await SchoolMethodAssociationService.get_settings_page_data(
            db,
            school_id=school_id,
        )
    )

    return render(
        templates,
        request,
        "school_admin/method_associations.html",
        {
            "user": user,
            **asdict(page_data),
            "error": get_error_message(request),
            "success": (
                    request.query_params.get("success") == "1"
            ),
        },
    )


@router.post(
    "/method-associations",
    name="school_method_association_settings_save",
)
async def school_method_association_settings_save(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_school_admin_scope),
):
    """
    Сохраняет выбранные методические объединения школы.
    """

    school_id = cast(
        int | None,
        getattr(user, "school_id", None),
    )

    redirect_url = request.url_for(
        "school_method_association_settings_page"
    )

    if school_id is None:
        return RedirectResponse(
            url=f"{redirect_url}?error=school_not_found",
            status_code=303,
        )

    form = await request.form()

    selected_codes = [
        str(code)
        for code in form.getlist("selected_codes")
    ]

    version_value = form.get("settings_version")
    settings_version = version_value if isinstance(version_value, str) else ""
    form_user = _normalize_user(user)
    try:
        await SchoolMethodAssociationService.update_settings(
            db,
            school_id=school_id,
            selected_codes=selected_codes,
            expected_version=settings_version,
        )

    except (MethodAssociationSettingsConflict, IntegrityError) as exc:
        await db.rollback()
        page_data = await SchoolMethodAssociationService.get_settings_page_data(db, school_id=school_id)
        return render_error(
            templates, request, "school_admin/method_associations.html",
            {"user": form_user, **asdict(page_data), "success": False},
            error=(
                "Сохранённые методические объединения содержат конфликтующие записи. Обратитесь к администратору."
                if isinstance(exc, (MethodAssociationDataConflict, IntegrityError)) else
                "Настройки изменились в другой вкладке. Показан текущий выбор. Проверьте его перед сохранением."
            ),
            status_code=409,
        )

    except ValueError:
        await db.rollback()

        return RedirectResponse(
            url=f"{redirect_url}?error=invalid_codes",
            status_code=303,
        )

    except Exception:
        await db.rollback()
        raise

    return RedirectResponse(
        url=f"{redirect_url}?success=1",
        status_code=303,
    )
