# app/routers/web/reports/user_template_web.py
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.reports.repositories.lesson_observation_report_repo import LessonObservationRepo
from app.modules.reports.repositories.template_repo import TemplateReportRepo
from app.modules.reports.repositories.user_template_repo import UserReportTemplateRepo
from app.modules.reports.services.lesson_observation_report_service import LessonObservationReportService, \
    LessonObservationService
from app.modules.reports.services.user_template_service import UserReportTemplateService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/staff/reports/templates/my",
    tags=["user-templates"],
)


# =========================
# LIST
# =========================
@router.get("", name="staff_user_templates_page", response_class=HTMLResponse)
async def list_templates(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF)),
):
    """
    Страница создания личного шаблона.

    Отображает:
    - форму конструктора (разделы + критерии);
    - общую информацию шаблона.

    Ничего не сохраняет.
    """
    templates_list = await UserReportTemplateService.list_my_templates(
        db,
        owner_user_id=user.id,
    )

    return templates.TemplateResponse(
        "staff/reports/user_templates/template_list.html",
        {
            "request": request,
            "user": user,
            "templates_list": templates_list,
        },
    )


# =========================
# CREATE PAGE
# =========================
@router.get("/new", name="staff_user_template_create_page", response_class=HTMLResponse)
async def create_template_page(request: Request):
    """
        Создание личного шаблона пользователя.

        Принимает:
        - report_code;
        - title, description;
        - schema_json — JSON-структуру конструктора шаблона.

        Сохраняет:
        - UserReportTemplate.schema_json.
        """

    page_context = UserReportTemplateService.get_constructor_page_context(
        report_code=request.query_params.get("report_code"),
        month_item_id=request.query_params.get("month_item_id"),
        selected_report_id=request.query_params.get("selected_report_id"),
    )

    return templates.TemplateResponse(
        page_context["template_name"],
        {
            "request": request,
            "template": None,
            **page_context,
        },
    )


# =========================
# CREATE
# =========================
@router.post("/new", name="staff_user_template_create")
async def create_template(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF)),
):
    """
    Создание личного шаблона пользователя.

    Принимает:
    - report_code;
    - title, description;
    - schema_json — JSON-структуру конструктора шаблона.

    Сохраняет:
    - UserReportTemplate.schema_json.

    Важно:
    - context_month_item_id и context_selected_report_id не относятся к самому шаблону;
    - они нужны только для возврата пользователя обратно в поток задачи;
    - если пользователь пришел из конкретной задачи, после сохранения возвращаем его
      на страницу "Мои шаблоны" с тем же контекстом.
    """
    form = await request.form()

    await UserReportTemplateService.create_my_template(
        db,
        owner_user_id=user.id,
        report_code=form.get("report_code"),
        title=form.get("title"),
        description=form.get("description"),
        schema_json=form.get("schema_json"),
    )

    month_item_id = form.get("context_month_item_id")
    selected_report_id = form.get("context_selected_report_id")

    query = {}
    if month_item_id and selected_report_id:
        query["month_item_id"] = month_item_id
        query["selected_report_id"] = selected_report_id
    query["success"] = "Шаблон создан"

    redirect_url = str(request.url_for("staff_user_templates_page"))
    if query:
        redirect_url += "?" + urlencode(query)

    return RedirectResponse(
        url=redirect_url,
        status_code=303,
    )


# =========================
# EDIT PAGE
# =========================
@router.get(
    "/{template_id}/edit",
    name="staff_user_template_edit_page",
    response_class=HTMLResponse,
)
async def edit_template_page(
        request: Request,
        template_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF)),
):
    page_data = await UserReportTemplateService.get_my_template_edit_page_data(
        db,
        template_id=template_id,
        owner_user_id=user.id,
    )

    return templates.TemplateResponse(
        page_data["template_path"],
        {
            "request": request,
            "user": user,
            **page_data,

            "month_item_id": request.query_params.get("month_item_id"),
            "selected_report_id": request.query_params.get("selected_report_id"),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


# =========================
# UPDATE
# =========================
@router.post(
    "/{template_id}/edit",
    name="staff_user_template_update",
)
async def update_template(
        request: Request,
        template_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF)),
):
    form = await request.form()

    await UserReportTemplateService.update_my_template(
        db,
        template_id=template_id,
        owner_user_id=user.id,
        title=form.get("title"),
        description=form.get("description"),
        schema_json=form.get("schema_json"),
    )

    month_item_id = form.get("context_month_item_id")
    selected_report_id = form.get("context_selected_report_id")

    query = {
        "success": "Шаблон сохранен",
    }

    if month_item_id and selected_report_id:
        query["month_item_id"] = month_item_id
        query["selected_report_id"] = selected_report_id

    redirect_url = (
            str(request.url_for("staff_user_templates_page"))
            + "?"
            + urlencode(query)
    )

    return RedirectResponse(
        url=redirect_url,
        status_code=303,
    )


# =========================
# SELECT
# =========================
@router.get(
    "/{month_item_id}/templates/{selected_report_id}/my",
    name="staff_user_template_select_page",
    response_class=HTMLResponse,
)
async def staff_user_template_select_page(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    """
    Страница выбора личного шаблона для конкретного выбранного отчета.

    Показывает:
    - список личных шаблонов пользователя (фильтр по report_code)
    - информацию о выбранном отчете (report_code, label, target)
    """

    try:
        # 1. Получаем выбранный отчет
        selected_report = await TemplateReportRepo.get_selected_report(
            db,
            selected_report_id=selected_report_id,
        )

        if not selected_report:
            raise ValueError("Выбранный отчет не найден.")

        if not selected_report.report_type:
            raise ValueError("У выбранного отчета не указан тип.")

        report_type = selected_report.report_type
        report_code = report_type.code
        report_label = report_type.name_kz or report_type.name_ru or report_type.code

        # 2. Получаем список личных шаблонов пользователя по типу отчета
        templates_list = await UserReportTemplateService.list_my_templates(
            db,
            owner_user_id=user.id,
            report_code=report_code,
        )

        return templates.TemplateResponse(
            "staff/reports/user_templates/template_select.html",
            {
                "request": request,
                "user": user,

                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,

                "report_code": report_code,
                "report_label": report_label,

                "target_kind": selected_report.target_kind,
                "target_value": selected_report.target_value,
                "target_label": selected_report.target_label,

                "templates_list": templates_list,

                "error": request.query_params.get("error"),
                "success": request.query_params.get("success"),
            },
        )

    except ValueError as e:
        return templates.TemplateResponse(
            "staff/reports/user_templates/template_select.html",
            {
                "request": request,
                "user": user,

                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,

                "report_code": None,
                "report_label": None,

                "target_kind": None,
                "target_value": None,
                "target_label": None,

                "templates_list": [],

                "error": str(e),
                "success": None,
            },
            status_code=404,
        )


# Применения выбранного личного шаблона отчета к задаче
@router.post(
    "/{month_item_id}/templates/{selected_report_id}/my/apply",
    name="staff_report_apply_my_template",
)
async def staff_report_apply_my_template(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    """
    Применение личного шаблона к отчету задачи.

    Делает:
    - находит TaskExecutionDocument;
    - копирует schema_json из UserReportTemplate;
    - сохраняет snapshot в document.schema_json;
    - устанавливает template_mode = CUSTOM.

    Важно:
    - это НЕ ссылка, а копия структуры;
    - изменения шаблона в будущем не влияют на документ.

    После применения:
    → редирект на страницу заполнения отчета.
    """
    form = await request.form()
    template_id = int(form.get("template_id"))

    template = await UserReportTemplateRepo.get_user_template(
        db,
        template_id=template_id,
        owner_user_id=user.id,
    )

    if not template:
        return RedirectResponse(
            url=str(
                request.url_for(
                    "staff_user_template_select_page",
                    month_item_id=month_item_id,
                    selected_report_id=selected_report_id,
                )
            ) + "?error=Шаблон не найден",
            status_code=303,
        )

    await UserReportTemplateService.apply_my_template(
        db,
        month_item_id=month_item_id,
        selected_report_id=selected_report_id,
        user_id=user.id,
        template_id=template_id,
    )

    if template.report_code == "lesson_observation":
        route_name = "staff_user_lesson_observation_fill_page"

    elif template.report_code == "checking_notebooks_table":
        route_name = "checking_notebooks_fill_page"

    else:
        return RedirectResponse(
            url=str(
                request.url_for(
                    "staff_user_template_select_page",
                    month_item_id=month_item_id,
                    selected_report_id=selected_report_id,
                )
            ) + f"?error=Тип отчета не поддерживается: {template.report_code}",
            status_code=303,
        )

    return RedirectResponse(
        url=request.url_for(
            route_name,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        ),
        status_code=303,
    )


# =========================
# DELETE
# =========================
@router.post("/{template_id}/delete", name="staff_user_template_delete")
async def delete_template(
        template_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF)),
):
    await UserReportTemplateService.delete_my_template(
        db,
        template_id=template_id,
        owner_user_id=user.id,
    )

    return RedirectResponse(
        url="/staff/reports/templates/my",
        status_code=303,
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
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    """
       Страница заполнения листа наблюдения по личному шаблону.

       Использует:
       - TaskExecutionDocument.schema_json как snapshot структуры формы;
       - LessonObservationReport.criteria_scores как сохраненные ответы.
       """
    try:
        page_data = await LessonObservationReportService.get_lesson_observation_fill_page_data(
            db,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            user=user,
        )

        return templates.TemplateResponse(
            "staff/reports/user_templates/fill_lesson_observation.html",
            {
                "request": request,
                "user": user,

                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,

                "document": page_data.document,
                "report": page_data.report,
                "schema": page_data.schema,
                "scores": page_data.scores,
                "total_score": page_data.total_score,

                # важно: шаблон ожидает saved_info
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
            },
        )

    except ValueError as e:
        return templates.TemplateResponse(
            "staff/reports/user_templates/fill_lesson_observation.html",
            {
                "request": request,
                "user": user,

                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,

                "document": None,
                "report": None,
                "schema": {},
                "scores": {},
                "saved_info": {},
                "total_score": 0,
                "info_labels": {},
                "error": str(e),
            },
            status_code=404,
        )


# POST-роут для сохранения введенных данных личного выбранного шаблона отчета
@router.post(
    "/{month_item_id}/templates/{selected_report_id}/lesson-observation/fill",
    name="staff_user_lesson_observation_fill_submit",
)
async def staff_user_lesson_observation_fill_submit(
        request: Request,
        month_item_id: int,
        selected_report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    form = await request.form()

    action = form.get("action")

    await LessonObservationReportService.save_lesson_observation_draft(
        db,
        month_item_id=month_item_id,
        selected_report_id=selected_report_id,
        user=user,
        form=form,
    )

    # 🔥 разное поведение
    if action == "complete":
        await LessonObservationReportService.complete_report(
            db,
            selected_report_id=selected_report_id,
            user=user,
        )

        return RedirectResponse(
            url=request.url_for("staff_report_done_page"),
            status_code=303,
        )

    # default = save
    return RedirectResponse(
        url=request.url_for(
            "staff_user_lesson_observation_fill_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        ),
        status_code=303,
    )


@router.post(
    "/{month_item_id}/documents/{document_id}/lesson-observation/save",
    name="lesson_observation_save_post",
)
async def lesson_observation_save_post(
        request: Request,
        month_item_id: int,
        document_id: int,
        selected_report_id: int = Query(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    form = await request.form()

    try:
        report = await LessonObservationService.save_or_complete(
            db,
            request=request,
            form=form,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
            task_execution_document_id=document_id,
            user=user,
            templates=templates,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if form.get("action") == "complete":
        redirect_url = request.url_for(
            "staff_user_lesson_observation_fill_page",
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )

        redirect_url = (
            f"{redirect_url}?"
            f"{urlencode({'success': 'Отчет сохранен и подписан.'})}"
        )

        return RedirectResponse(
            redirect_url,
            status_code=303,
        )

    redirect_url = request.url_for(
        "staff_user_lesson_observation_fill_page",
        month_item_id=month_item_id,
        selected_report_id=selected_report_id,
    )

    redirect_url = (
        f"{redirect_url}?"
        f"{urlencode({'success': 'Черновик сохранен.'})}"
    )

    return RedirectResponse(
        redirect_url,
        status_code=303,
    )


@router.get(
    "/lesson-observation/{report_id}/pdf/view",
    name="lesson_observation_pdf_view",
)
async def lesson_observation_pdf_view(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    report = await LessonObservationRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Отчет не найден")

    if report.observer_user_id != user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к отчету")

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF не найден")

    pdf_path = Path(str(pdf_file))

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF-файл отсутствует на сервере")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"lesson_observation_{report.id}.pdf",
        headers={
            "Content-Disposition": f'inline; filename="lesson_observation_{report.id}.pdf"'
        },
    )


@router.get(
    "/lesson-observation/{report_id}/pdf/download",
    name="lesson_observation_pdf_download",
)
async def lesson_observation_pdf_download(
        report_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_STAFF, UserRole.SCHOOL_ADMIN)),
):
    report = await LessonObservationRepo.get_by_id(db, report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Отчет не найден")

    if report.observer_user_id != user.id:
        raise HTTPException(status_code=403, detail="Нет доступа к отчету")

    pdf_file = report.pdf_signed_file

    if not pdf_file:
        raise HTTPException(status_code=404, detail="PDF не найден")

    pdf_path = Path(str(pdf_file))

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF-файл отсутствует на сервере")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"lesson_observation_{report.id}.pdf",
        headers={
            "Content-Disposition": f'attachment; filename="lesson_observation_{report.id}.pdf"'
        },
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
