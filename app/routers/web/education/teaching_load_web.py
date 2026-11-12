# app/routers/web/education/teaching_load_web.py

from __future__ import annotations

from typing import cast
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.education.schemas.teaching_load import (
    TeachingLoadCreateDTO,
)
from app.modules.education.services.teaching_load_service import (
    TeachingLoadError,
    TeachingLoadService,
)
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/education/teaching-load",
    tags=["education-teaching-load"],
)


# ============================================================
# HELPERS
# ============================================================

def _get_school_id(user: User) -> int:
    """
    Получить school_id текущего администратора школы.
    """

    school_id = cast(
        int | None,
        user.school_id,
    )

    if school_id is None:
        raise HTTPException(
            status_code=403,
            detail="Мектеп анықталмады.",
        )

    return school_id


def _redirect_to_page(
        request: Request,
        *,
        academic_year_start: int,
        success: str | None = None,
        error: str | None = None,
) -> RedirectResponse:
    """
    PRG redirect обратно на страницу нагрузки.
    """

    url = str(
        request.url_for(
            "school_teaching_load_page"
        )
    )

    params: dict[str, str | int] = {
        "academic_year_start": academic_year_start,
    }

    if success:
        params["success"] = success

    if error:
        params["error"] = error

    return RedirectResponse(
        url=f"{url}?{urlencode(params)}",
        status_code=303,
    )


# ============================================================
# PAGE
# ============================================================

@router.get(
    "",
    name="school_teaching_load_page",
    response_class=HTMLResponse,
)
async def school_teaching_load_page(
        request: Request,
        academic_year_start: int = 2026,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Страница управления педагогической нагрузкой школы.
    """

    school_id = _get_school_id(user)

    try:
        page = await TeachingLoadService.get_page(
            db,
            school_id=school_id,
            academic_year_start=academic_year_start,
        )

    except TeachingLoadError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return render(
        templates,
        request,
        "education/teaching_load.html",
        {
            "user": user,
            "page": page,
            "success": request.query_params.get(
                "success"
            ),
            "error": request.query_params.get(
                "error"
            ),
        },
    )


# ============================================================
# CREATE
# ============================================================

@router.post(
    "/create",
    name="school_teaching_load_create",
)
async def school_teaching_load_create(
        request: Request,
        academic_year_start: int = Form(...),
        school_class_id: int = Form(...),
        subject_id: int = Form(...),
        staff_member_id: int = Form(...),
        is_primary: bool = Form(False),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Назначить преподавателя:

        класс + предмет + сотрудник.
    """

    school_id = _get_school_id(user)

    dto = TeachingLoadCreateDTO(
        school_class_id=school_class_id,
        subject_id=subject_id,
        staff_member_id=staff_member_id,
        is_primary=is_primary,
    )

    try:
        await TeachingLoadService.create_assignment(
            db,
            school_id=school_id,
            dto=dto,
        )

    except TeachingLoadError as exc:
        return _redirect_to_page(
            request,
            academic_year_start=academic_year_start,
            error=str(exc),
        )

    return _redirect_to_page(
        request,
        academic_year_start=academic_year_start,
        success="Оқу жүктемесі сәтті тағайындалды.",
    )


# ============================================================
# DEACTIVATE
# ============================================================

@router.post(
    "/{assignment_id}/deactivate",
    name="school_teaching_load_deactivate",
)
async def school_teaching_load_deactivate(
        request: Request,
        assignment_id: int,
        academic_year_start: int = Form(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Снять активное назначение.

    Запись физически не удаляется.
    """

    school_id = _get_school_id(user)

    try:
        await TeachingLoadService.deactivate_assignment(
            db,
            school_id=school_id,
            assignment_id=assignment_id,
        )

    except TeachingLoadError as exc:
        return _redirect_to_page(
            request,
            academic_year_start=academic_year_start,
            error=str(exc),
        )

    return _redirect_to_page(
        request,
        academic_year_start=academic_year_start,
        success="Оқу жүктемесі тоқтатылды.",
    )
