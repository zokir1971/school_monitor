# app/routers/web/reports/lesson_observation_web.py
from dataclasses import asdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.reports.repositories.lesson_observation_repo import LessonObservationRepo
from app.modules.reports.services.lesson_observation_service import LessonObservationService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render, render_error
from app.utils.storage import resolve_storage_file

router = APIRouter(
    prefix="/staff/reports/templates/my",
    tags=["user-templates"],
)


@router.get(
    "/{month_item_id}/templates/{selected_report_id}/lesson-observation/fill",
    name="staff_user_lesson_observation_fill_page",
    response_class=HTMLResponse,
)
async def staff_user_lesson_observation_fill_page(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        template_id: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Страница заполнения листа наблюдения.

    Новая архитектура:
    - GET является read-only;
    - TaskExecutionDocument может отсутствовать до первого Save/Complete;
    - template_id=None -> системный preview;
    - template_id=int  -> пользовательский preview;
    - существующий document.schema_json является snapshot
      и имеет приоритет над template_id.
    """

    try:
        page_data = (
            await LessonObservationService
            .get_lesson_observation_fill_page_data(
                db,
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
                template_id=template_id,
                user=user,
            )
        )

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "staff/reports/user_templates/fill_lesson_observation.html",
            {
                "user": user,

                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,
                "template_id": template_id,

                "document": None,
                "report": None,
                "schema": {},
                "scores": {},
                "saved_info": {},
                "total_score": 0,
                "info_labels": {},
            },
            error=str(exc),
            status_code=404,
        )

    return render(
        templates,
        request,
        "staff/reports/user_templates/fill_lesson_observation.html",
        {
            "user": user,

            "month_item_id": page_data.month_item_id,
            "selected_report_id": page_data.selected_report_id,
            "template_id": template_id,

            "document": page_data.document,
            "report": page_data.report,
            "schema": page_data.schema,
            "scores": page_data.scores,
            "total_score": page_data.total_score,

            "saved_info": asdict(page_data.info),

            "info_labels": {
                "teacher_name": "Педагогтің ТАӘ",
                "teacher_post": "Лауазымы, біліктілік санаты",
                "subject": "Пән",
                "organization": "Білім беру ұйымы",
                "class_group": "Сынып / топ",
                "controller_name": "Бақылаушының ТАӘ",
                "controller_post": "Бақылаушының лауазымы",
                "lesson_datetime": "Уақыты",
                "theme": "Сабақтың тақырыбы",
                "learning_objectives": "Оқу мақсаты",
            },

            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post(
    "/{month_item_id}/templates/{selected_report_id}/lesson-observation/fill",
    name="staff_user_lesson_observation_fill_submit",
)
async def staff_user_lesson_observation_fill_submit(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        template_id: int | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    """
    Сохранение/подписание листа наблюдения.

    TaskExecutionDocument при первом сохранении создается внутри
    LessonObservationService.save_or_complete().
    """

    form = await request.form()

    try:
        await LessonObservationService.save_or_complete(
            db,
            request=request,
            form=form,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
            templates=templates,
            template_id=template_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    action = str(
        form.get("action") or "save"
    ).strip()

    month = request.query_params.get("month")

    if action == "complete":
        templates_page_url = str(
            request.url_for(
                "staff_report_templates_page",
                month_item_id=month_item_id,
            )
        )

        query: dict[str, str] = {
            "success": "Отчет сохранен и подписан.",
        }

        if month:
            query["month"] = month

        return RedirectResponse(
            url=f"{templates_page_url}?{urlencode(query)}",
            status_code=303,
        )

    fill_page_url = str(
        request.url_for(
            "staff_user_lesson_observation_fill_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )
    )

    query: dict[str, str | int] = {
        "success": "Черновик сохранен.",
    }

    if template_id is not None:
        query["template_id"] = template_id

    if month:
        query["month"] = month

    return RedirectResponse(
        url=f"{fill_page_url}?{urlencode(query)}",
        status_code=303,
    )


@router.get(
    "/lesson-observation/{report_id}/pdf/view",
    name="lesson_observation_pdf_view",
)
async def lesson_observation_pdf_view(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    report = await LessonObservationRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Отчет не найден",
        )

    if report.observer_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Нет доступа к отчету",
        )

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(
            status_code=404,
            detail="PDF не найден",
        )

    pdf_path = resolve_storage_file(str(pdf_file))

    filename = f"lesson_observation_{report.id}.pdf"

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


@router.get(
    "/lesson-observation/{report_id}/pdf/download",
    name="lesson_observation_pdf_download",
)
async def lesson_observation_pdf_download(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
                UserRole.SCHOOL_ADMIN,
            )
        ),
):
    report = await LessonObservationRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(
            status_code=404,
            detail="Отчет не найден",
        )

    if report.observer_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="Нет доступа к отчету",
        )

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(
            status_code=404,
            detail="PDF не найден",
        )

    pdf_path = resolve_storage_file(str(pdf_file))

    filename = f"lesson_observation_{report.id}.pdf"

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="attachment",
    )


@router.get(
    "/lesson-observation/verify",
    name="lesson_observation_verify_page",
    response_class=HTMLResponse,
)
async def lesson_observation_verify_page(
        request: Request,
        token: str,
):
    url = request.url_for("report_verify_page").include_query_params(token=token)
    return RedirectResponse(url=str(url), status_code=302)
