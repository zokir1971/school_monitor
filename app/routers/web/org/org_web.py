from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.modules.org.repo import OrgRepo
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router = APIRouter(prefix="/schools", tags=["schools-web"])


# страница формирование школ
@router.get("/", name="schools_page", response_class=HTMLResponse)
async def schools_page(
        request: Request,
        region_id: int | None = Query(default=None),
        district_id: int | None = Query(default=None),
        settlement: str | None = Query(default=None),
        q: str | None = Query(default=None),
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

    schools = []
    should_show_schools = bool(region_id and district_id and settlement)

    if should_show_schools:
        schools = await OrgRepo.list_schools(
            db,
            region_id=region_id,
            district_id=district_id,
            settlement=settlement,
            q=q,
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
            "success": success,
            "error": error,
            "should_show_schools": should_show_schools,
        },
    )


# Страница создания школы
@router.get("/create", name="school_create_page", response_class=HTMLResponse)
async def school_create_page(
        request: Request,
        region_id: int | None = Query(default=None),
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
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    try:
        school = await OrgRepo.create_school(
            db,
            district_id=district_id,
            name=name,
            address=address,
        )
    except ValueError as exc:
        regions = await OrgRepo.list_regions(db)
        districts = await OrgRepo.list_districts(db, region_id=region_id)

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
                "error": str(exc),
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
        raise HTTPException(status_code=404, detail="Школа не найдена")

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
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SUPERUSER)),
):
    school = await OrgRepo.get_school(db, school_id=school_id)
    if not school:
        raise HTTPException(status_code=404, detail="Школа не найдена")

    try:
        await OrgRepo.update_school(
            db,
            school=school,
            district_id=district_id,
            name=name,
            address=address,
        )
    except ValueError as exc:
        regions = await OrgRepo.list_regions(db)
        districts = await OrgRepo.list_districts(db, region_id=region_id)

        fake_school = school
        fake_school.name = name
        fake_school.address = address
        fake_school.district_id = district_id

        return render(
            templates,
            request,
            "admin/school_form.html",
            {
                "user": user,
                "page_title": "Редактировать школу",
                "regions": regions,
                "districts": districts,
                "selected_region_id": region_id,
                "school": fake_school,
                "error": str(exc),
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
        raise HTTPException(status_code=404, detail="Школа не найдена")

    await OrgRepo.delete_school(db, school)

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
    if school_ids:
        await OrgRepo.delete_schools_bulk(db, school_ids=school_ids)

    return RedirectResponse(
        url=request.url_for("schools_page"),
        status_code=status.HTTP_303_SEE_OTHER,
    )
