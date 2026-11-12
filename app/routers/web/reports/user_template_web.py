# app/routers/web/reports/user_template_web.py
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.reports.services.user_template_service import UserReportTemplateService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render, render_error

router = APIRouter(
    prefix="/staff/reports/templates/my",
    tags=["user-templates"],
)


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

    return render(
        templates,
        request,
        "staff/reports/user_templates/template_list.html",
        {
            "user": user,
            "templates_list": templates_list,
        },
    )


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

    try:
        page_context = UserReportTemplateService.get_constructor_page_context(
            report_code=request.query_params.get("report_code"),
            month_item_id=request.query_params.get("month_item_id"),
            selected_report_id=request.query_params.get("selected_report_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return render(
        templates,
        request,
        page_context["template_name"],
        {
            "template": None,
            **page_context,
        },
    )


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

    try:
        await UserReportTemplateService.create_my_template(
            db,
            owner_user_id=user.id,
            report_code=form.get("report_code"),
            title=form.get("title"),
            description=form.get("description"),
            schema_json=form.get("schema_json"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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

    return render(
        templates,
        request,
        page_data["template_path"],
        {
            "user": user,
            **page_data,

            "month_item_id": request.query_params.get("month_item_id"),
            "selected_report_id": request.query_params.get("selected_report_id"),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


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
        page_data = (
            await UserReportTemplateService
            .get_template_selection_page_data(
                db,
                selected_report_id=selected_report_id,
                owner_user_id=user.id,
            )
        )

        return render(
            templates,
            request,
            "staff/reports/user_templates/template_select.html",
            {
                "user": user,
                "month_item_id": month_item_id,
                **page_data,
                "error": request.query_params.get("error"),
                "success": request.query_params.get("success"),
            },
        )

    except ValueError as e:
        return render_error(
            templates,
            request,
            "staff/reports/user_templates/template_select.html",
            {
                "user": user,

                "month_item_id": month_item_id,
                "selected_report_id": selected_report_id,

                "report_code": None,
                "report_label": None,

                "target_kind": None,
                "target_value": None,
                "target_label": None,

                "templates_list": [],
                "success": None,
            },
            error=str(e),
            status_code=404,
        )


@router.post(
    "/{month_item_id}/templates/{selected_report_id}/my/apply",
    name="staff_report_apply_my_template",
)
async def staff_report_apply_my_template(
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
    """
    Выбрать пользовательский шаблон для preview отчета.

    Новая архитектура:
    - НЕ создает TaskExecutionDocument;
    - НЕ копирует schema_json в документ;
    - НЕ делает apply/commit;
    - только проверяет доступ к шаблону и переводит пользователя
      в единый fill-route с template_id.

    Snapshot шаблона будет создан только при Save/Complete.
    """

    form = await request.form()

    try:
        template_id = int(
            form.get("template_id")
        )
    except (TypeError, ValueError):
        template_id = 0

    if template_id <= 0:
        redirect_url = str(
            request.url_for(
                "staff_user_template_select_page",
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
            )
        )

        return RedirectResponse(
            url=f"{redirect_url}?error=Не выбран шаблон",
            status_code=303,
        )

    try:
        template = await UserReportTemplateService.get_my_template(
            db,
            template_id=template_id,
            owner_user_id=user.id,
        )

    except ValueError:
        redirect_url = str(
            request.url_for(
                "staff_user_template_select_page",
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
            )
        )

        return RedirectResponse(
            url=f"{redirect_url}?error=Шаблон не найден",
            status_code=303,
        )

    route_map = {
        "lesson_observation":
            "staff_user_lesson_observation_fill_page",

        "checking_notebooks_table":
            "checking_notebooks_fill_page",
    }

    route_name = route_map.get(
        template.report_code
    )

    if route_name is None:
        redirect_url = str(
            request.url_for(
                "staff_user_template_select_page",
                month_item_id=month_item_id,
                selected_report_id=selected_report_id,
            )
        )

        return RedirectResponse(
            url=(
                f"{redirect_url}"
                f"?error=Тип отчета не поддерживается: "
                f"{template.report_code}"
            ),
            status_code=303,
        )

    fill_url = str(
        request.url_for(
            route_name,
            month_item_id=month_item_id,
            selected_report_id=selected_report_id,
        )
    )

    query: dict[str, str | int] = {
        "template_id": template_id,
    }

    month = request.query_params.get("month")

    if month:
        query["month"] = month

    return RedirectResponse(
        url=f"{fill_url}?{urlencode(query)}",
        status_code=303,
    )


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
