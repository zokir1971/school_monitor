# app/routers/web/planning/superuser_web.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import HTMLResponse

from app.modules.planning.models import PlanDirection, PlanTemplate, PlanTemplateRow11, PlanTemplateRow4
from app.modules.planning.repo import PlanDirectionRepo, PlanTemplateDirectionRepo
from app.modules.planning.services.superuser_service import SuperuserBuilderService
from app.modules.users.deps import require_roles, get_db
from app.modules.users.enums import UserRole
from app.routers.web.helpers.render import render, render_error
from app.routers.web.web_common import templates

router = APIRouter(prefix="/planning/super", tags=["planning.superuser.web"])


# =========================================================
# Directions (WEB)
# =========================================================
@router.get("/directions", response_class=HTMLResponse)
async def super_directions_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SUPERUSER)),
):
    directions = await PlanDirectionRepo.list_all(db)

    # ✅ активный шаблон (может быть None)
    active_template_id = await db.scalar(
        select(PlanTemplate.id)
        .where(PlanTemplate.is_active == True)
        .limit(1)
    )

    return render(
        templates,
        request,
        "planning/super/directions.html",
        {
            "user": user,
            "directions": directions,
            "active_template_id": active_template_id,
        },
    )


@router.get("/directions/add", response_class=HTMLResponse)
async def super_direction_add_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SUPERUSER)),
):
    active_template = await db.scalar(
        select(PlanTemplate)
        .where(PlanTemplate.is_active == True)
        .limit(1)
    )

    return render(
        templates,
        request,
        "planning/super/directions_add.html",
        {
            "user": user,
            "active_template": active_template,
        },
    )


@router.post("/templates/create")
async def super_template_create(
        name: str = Form(...),
        academic_year: str = Form(...),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SUPERUSER)),
):
    name = (name or "").strip()
    academic_year = (academic_year or "").strip()

    if not name or not academic_year:
        return RedirectResponse("/planning/super/directions/add", status_code=303)

    # сделать все шаблоны неактивными
    await db.execute(update(PlanTemplate).values(is_active=False))

    tpl = PlanTemplate(
        name=name,
        academic_year=academic_year,
        is_active=True,
        created_by_user_id=user.id,
    )
    db.add(tpl)
    await db.commit()

    # возвращаемся обратно на добавление направления
    return RedirectResponse("/planning/super/directions/add", status_code=303)


@router.post("/directions/add", response_class=HTMLResponse)
async def super_direction_add_submit(
        request: Request,
        short_title: str = Form(...),
        full_title: str | None = Form(None),
        is_active: str = Form("true"),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SUPERUSER)),
):
    st = (short_title or "").strip()
    ft = (full_title or "").strip() or None
    active_bool = (is_active == "true")

    if len(st) < 3:
        return render_error(
            templates,
            request,
            "planning/super/directions_add.html",
            {"user": user, "form": {"short_title": st, "full_title": ft or "", "is_active": is_active}},
            error="Короткое название должно быть не короче 3 символов.",
            status_code=400,
        )

    try:
        await PlanDirectionRepo.create(
            db,
            short_title=st,
            full_title=ft,
            is_active=active_bool,
            created_by_user_id=user.id,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        return render_error(
            templates,
            request,
            "planning/super/directions_add.html",
            {"user": user, "form": {"short_title": st, "full_title": ft or "", "is_active": is_active}},
            error=str(e),
            status_code=400,
        )

    return RedirectResponse(url="/planning/super/directions", status_code=303)


# =========================================================
# Удаление направления (карточек)
# =========================================================
@router.post("/directions/{direction_id}/delete")
async def super_direction_delete(
        direction_id: int,
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    await PlanDirectionRepo.delete(db, direction_id=direction_id)
    await db.commit()
    return RedirectResponse("/planning/super/directions", status_code=303)


@router.get("/builder", response_class=HTMLResponse)
async def super_builder_page(
        request: Request,
        template_id: int,
        direction_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SUPERUSER)),
):
    template = await db.get(PlanTemplate, template_id)
    direction = await db.get(PlanDirection, direction_id)

    ctx = await SuperuserBuilderService.build_page(
        db,
        template_id=template_id,
        direction_id=direction_id,
    )

    ctx.update({
        "user": user,
        "selected_template": template,
        "selected_direction": direction,
    })

    return render(
        templates,
        request,
        "planning/super/builder.html",
        ctx,
    )


@router.post("/builder/import")
async def super_builder_import(
        request: Request,
        template_id: int = Form(...),
        direction_id: int = Form(...),
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_db),
        user=Depends(require_roles(UserRole.SUPERUSER)),
):
    try:
        if not file.filename.lower().endswith(".docx"):
            return render_error(
                templates,
                request,
                "planning/super/builder.html",
                {
                    "user": user,
                    **(await SuperuserBuilderService.build_page(db, template_id=template_id, direction_id=direction_id))
                },
                "Загрузите файл .docx",
                status_code=400,
            )

        data = await file.read()
        c4, c11 = await SuperuserBuilderService.import_docx_two_tables_replace(
            db,
            template_id=template_id,
            direction_id=direction_id,
            file_bytes=data,
        )
        await db.commit()

        ctx = await SuperuserBuilderService.build_page(db, template_id=template_id, direction_id=direction_id)
        ctx.update({"user": user, "success": f"Импорт завершён: объектов={c4}, задач={c11}"})
        return render(templates, request, "planning/super/builder.html", ctx)

    except Exception as e:
        await db.rollback()
        ctx = await SuperuserBuilderService.build_page(db, template_id=template_id, direction_id=direction_id)
        ctx.update({"user": user})
        return render_error(
            templates,
            request,
            "planning/super/builder.html",
            ctx,
            f"Ошибка импорта: {e}",
            status_code=400,
        )


@router.post("/builder/rows4/add")
async def super_rows4_add(
        template_id: int = Form(...),
        direction_id: int = Form(...),
        control_object: str = Form(...),
        risk_text: str | None = Form(None),
        decision_text: str | None = Form(None),
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    td = await PlanTemplateDirectionRepo.get_or_create(db, template_id=template_id, direction_id=direction_id)

    # next order
    max_order = await db.scalar(
        select(func.max(PlanTemplateRow4.row_order)).where(PlanTemplateRow4.template_direction_id == td.id)
    )
    next_order = int(max_order or 0) + 1

    db.add(PlanTemplateRow4(
        template_direction_id=td.id,
        row_order=next_order,
        control_object=(control_object or "").strip(),
        risk_text=(risk_text or "").strip() or None,
        decision_text=(decision_text or "").strip() or None,
    ))
    await db.commit()

    return RedirectResponse(url=f"/planning/super/builder?template_id={template_id}&direction_id={direction_id}",
                            status_code=303)


@router.post("/builder/rows4/{row_id}/delete")
async def super_rows4_delete(
        row_id: int,
        template_id: int = Form(...),
        direction_id: int = Form(...),
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    await db.execute(delete(PlanTemplateRow4).where(PlanTemplateRow4.id == row_id))
    await db.commit()
    return RedirectResponse(url=f"/planning/super/builder?template_id={template_id}&direction_id={direction_id}",
                            status_code=303)


@router.post("/builder/rows11/add")
async def super_rows11_add(
        template_id: int = Form(...),
        direction_id: int = Form(...),
        topic: str = Form(...),
        goal: str | None = Form(None),
        control_object: str | None = Form(None),
        control_type: str | None = Form(None),
        methods: str | None = Form(None),
        deadlines: str | None = Form(None),
        responsibles: str | None = Form(None),
        review_place: str | None = Form(None),
        management_decision: str | None = Form(None),
        second_control: str | None = Form(None),
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    td = await PlanTemplateDirectionRepo.get_or_create(db, template_id=template_id, direction_id=direction_id)

    max_order = await db.scalar(
        select(func.max(PlanTemplateRow11.row_order)).where(PlanTemplateRow11.template_direction_id == td.id)
    )
    next_order = int(max_order or 0) + 1

    db.add(PlanTemplateRow11(
        template_direction_id=td.id,
        row_order=next_order,
        topic=(topic or "").strip(),
        goal=(goal or "").strip() or None,
        control_object=(control_object or "").strip() or None,
        control_type=(control_type or "").strip() or None,
        methods=(methods or "").strip() or None,
        deadlines=(deadlines or "").strip() or None,
        responsibles=(responsibles or "").strip() or None,
        review_place=(review_place or "").strip() or None,
        management_decision=(management_decision or "").strip() or None,
        second_control=(second_control or "").strip() or None,
    ))
    await db.commit()

    return RedirectResponse(url=f"/planning/super/builder?template_id={template_id}&direction_id={direction_id}",
                            status_code=303)


@router.post("/builder/rows11/{row_id}/delete")
async def super_rows11_delete(
        row_id: int,
        template_id: int = Form(...),
        direction_id: int = Form(...),
        db: AsyncSession = Depends(get_db),
        _user=Depends(require_roles(UserRole.SUPERUSER)),
):
    await db.execute(delete(PlanTemplateRow11).where(PlanTemplateRow11.id == row_id))
    await db.commit()
    return RedirectResponse(url=f"/planning/super/builder?template_id={template_id}&direction_id={direction_id}",
                            status_code=303)
