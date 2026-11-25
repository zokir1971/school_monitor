from __future__ import annotations

from typing import Annotated
from pydantic import BeforeValidator

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from starlette import status

from app.core.i18n import resolve_language
from app.core.schools_i18n import school_feedback
from app.db.session import get_db
from app.modules.org.repo import OrgRepo
from typing import Literal
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render, _normalize_user
from app.routers.web.web_common import templates

def _empty_filter_to_none(value):
    # HTML GET forms submit unselected <option value=""> fields as empty strings.
    if isinstance(value, str) and not value.strip():
        return None
    return value


OptionalFilterId = Annotated[int | None, BeforeValidator(_empty_filter_to_none), Query()]


router = APIRouter(prefix="/schools", tags=["schools-web"])


# страница формирование школ
@router.get("/", name="schools_page", response_class=HTMLResponse)
async def schools_page(
    request: Request,
    region_id: OptionalFilterId = None,
    district_id: OptionalFilterId = None,
    settlement: str | None = Query(default=None),
    q: str | None = Query(default=None),
    governance_level: Literal["", "district", "region"] | None = Query(default=None),
    success: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    regions = await OrgRepo.list_regions(db)

    districts = []
    if region_id is not None:
        districts = await OrgRepo.list_districts(db, region_id=region_id)

    settlements = []
    if district_id is not None:
        settlements = await OrgRepo.list_settlements(db, district_id=district_id)

    q = (q or "").strip() or None
    settlement = (settlement or "").strip() or None
    schools = []
    should_show_schools = bool(
        q or region_id is not None or district_id is not None or settlement or governance_level
    )
    language = resolve_language(request, user)
    search_labels = {
        "hint": "Введите название школы или выберите фильтры и нажмите «Применить». Населённый пункт выбирать необязательно.",
        "empty": "Школы по заданным условиям не найдены",
        "settlement": "Населённый пункт",
    } if language != "kk" else {
        "hint": "Мектеп атауын енгізіңіз немесе сүзгілерді таңдап, «Қолдану» түймесін басыңыз. Елді мекенді таңдау міндетті емес.",
        "empty": "Берілген шарттар бойынша мектептер табылмады",
        "settlement": "Елді мекен",
    }

    if should_show_schools:
        schools = await OrgRepo.list_schools(
            db,
            region_id=region_id,
            district_id=district_id,
            settlement=settlement,
            q=q,
            governance_level=governance_level or None,
        )

    return templates.TemplateResponse(
        request,
        "admin/schools.html",
        {
            "user": user,
            "regions": regions,
            "districts": districts,
            "settlements": settlements,
            "schools": schools,
            "selected_region_id": region_id,
            "selected_district_id": district_id,
            "selected_settlement": settlement,
            "q": q,
            "selected_governance_level": governance_level or "",
            "success": success,
            "error": error,
            "should_show_schools": should_show_schools,
            "search_labels": search_labels,
        },
    )


# Страница создания школы
@router.get("/create", name="school_create_page", response_class=HTMLResponse)
async def school_create_page(
    request: Request,
    region_id: OptionalFilterId = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    regions = await OrgRepo.list_regions(db)

    if region_id:
        districts = await OrgRepo.list_districts(db, region_id=region_id)
    else:
        districts = []

    return render(
        templates,
        request,
        "admin/school_form.html",
        {
            "user": user,
            "page_title": "Добавить школу",
            "regions": regions,
            "districts": districts,
            "selected_region_id": region_id,
            "school": None,
            "error": None,
        },
    )


@router.post("/create", name="school_create")
async def school_create(
    request: Request,
    region_id: int = Form(...),
    district_id: int = Form(...),
    name: str = Form(...),
    address: str | None = Form(default=None),
    governance_level: Literal["district", "region"] = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    form_user = _normalize_user(user)
    try:
        school = await OrgRepo.create_school(
            db,
            district_id=district_id,
            name=name,
            address=address,
            region_id=region_id,
            governance_level=governance_level,
        )
    except (ValueError, IntegrityError) as exc:
        regions = await OrgRepo.list_regions(db)
        districts = await OrgRepo.list_districts(db, region_id=region_id)

        return render(
            templates,
            request,
            "admin/school_form.html",
            {
                "user": form_user,
                "page_title": "Добавить школу",
                "regions": regions,
                "districts": districts,
                "selected_region_id": region_id,
                "school": dict(name=name, address=address, district_id=district_id, governance_level=governance_level),
                "is_create": True,
                "error": (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Не удалось выполнить действие. Проверьте данные школы и выбранные фильтры."
                ),
            },
            status_code=400,
        )

    return RedirectResponse(
        url=request.url_for("school_edit_page", school_id=school.id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# страница редактирование школ
@router.get("/{school_id}/edit", name="school_edit_page", response_class=HTMLResponse)
async def school_edit_page(
    school_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    school = await OrgRepo.get_school(db, school_id=school_id)
    if not school:
        raise HTTPException(
            status_code=404,
            detail=school_feedback("Школа не найдена", resolve_language(request)),
        )

    regions = await OrgRepo.list_regions(db)
    districts = await OrgRepo.list_districts(db, region_id=school.district.region_id)

    return render(
        templates,
        request,
        "admin/school_form.html",
        {
            "user": user,
            "page_title": "Редактировать школу",
            "regions": regions,
            "districts": districts,
            "selected_region_id": school.district.region_id,
            "school": school,
            "error": None,
        },
    )


# Обработка редактирования
@router.post("/{school_id}/edit", name="school_update")
async def school_update(
    school_id: int,
    request: Request,
    region_id: int = Form(...),
    district_id: int = Form(...),
    name: str = Form(...),
    address: str | None = Form(default=None),
    governance_level: Literal["district", "region"] = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    form_user = _normalize_user(user)
    school = await OrgRepo.get_school(db, school_id=school_id)
    if not school:
        raise HTTPException(
            status_code=404,
            detail=school_feedback("Школа не найдена", resolve_language(request)),
        )

    try:
        await OrgRepo.update_school(
            db,
            school=school,
            actor_user_id=user.id,
            district_id=district_id,
            name=name,
            address=address,
            region_id=region_id,
            governance_level=governance_level,
        )
    except (ValueError, IntegrityError) as exc:
        regions = await OrgRepo.list_regions(db)
        districts = await OrgRepo.list_districts(db, region_id=region_id)

        fake_school = dict(
            id=school_id, name=name, address=address, district_id=district_id, governance_level=governance_level
        )

        return render(
            templates,
            request,
            "admin/school_form.html",
            {
                "user": form_user,
                "page_title": "Редактировать школу",
                "regions": regions,
                "districts": districts,
                "selected_region_id": region_id,
                "school": fake_school,
                "error": (
                    str(exc)
                    if isinstance(exc, ValueError)
                    else "Не удалось выполнить действие. Проверьте данные школы и выбранные фильтры."
                ),
            },
            status_code=400,
        )

    return RedirectResponse(
        url=request.url_for("schools_page"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# Удаления одной школы
@router.post("/{school_id}/delete", name="school_delete")
async def school_delete(
    school_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    school = await OrgRepo.get_school(db, school_id=school_id)
    if not school:
        raise HTTPException(
            status_code=404,
            detail=school_feedback("Школа не найдена", resolve_language(request)),
        )

    language = resolve_language(request, _user)
    try:
        await OrgRepo.delete_school(db, school)
    except IntegrityError as exc:
        raise HTTPException(409, school_feedback(None, language)) from exc

    return RedirectResponse(
        url=request.url_for("schools_page"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# массивное удаления
@router.post("/delete-bulk", name="schools_delete_bulk")
async def schools_delete_bulk(
    request: Request,
    school_ids: list[int] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    language = resolve_language(request, _user)
    if school_ids:
        try:
            await OrgRepo.delete_schools_bulk(db, school_ids=school_ids)
        except IntegrityError as exc:
            raise HTTPException(409, school_feedback(None, language)) from exc

    return RedirectResponse(
        url=request.url_for("schools_page"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
