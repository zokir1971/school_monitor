# app/modules/reviews/routes/review_result_routes.py

from __future__ import annotations

from dataclasses import asdict

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi.responses import RedirectResponse

from app.core.storage.factory import get_storage
from app.db.session import get_db
from app.modules.planning.enums import ReviewPlace
from app.modules.reviews.services.review_result_service import (
    ReviewResultService,
)
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import (
    render,
    render_error,
)
from app.routers.web.helpers.request import parse_optional_int, parse_optional_bool
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/staff/reviews",
    tags=["Review results"],
)

# ==========================================================
# 1. Список задач и результатов рассмотрения
# ==========================================================
@router.get(
    "",
    name="review_result_list_page",
)
async def review_result_list_page(
    request: Request,

    school_id: str | None = Query(default=None),
    year: str | None = Query(default=None),
    month: str | None = Query(default=None),
    review_place: str | None = Query(default=None),
    reviewed: str | None = Query(default=None),
    task_review_id: str | None = Query(default=None),

    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF)),
):
    """
    Показывает список задач и результаты их рассмотрения.

    Для применения фильтров пользователь обязан выбрать
    место рассмотрения.
    """

    selected_school_id = parse_optional_int(
        school_id
    )

    selected_year = parse_optional_int(
        year
    )

    selected_month = parse_optional_int(
        month
    )

    selected_reviewed = parse_optional_bool(
        reviewed
    )

    selected_task_review_id = parse_optional_int(
        task_review_id
    )

    selected_review_place: ReviewPlace | None = None

    if review_place:
        normalized_review_place = review_place.strip()

        if normalized_review_place:
            try:
                selected_review_place = ReviewPlace(
                    normalized_review_place
                )
            except ValueError:
                selected_review_place = None

    # Проверяем именно факт отправки формы фильтров.
    # school_id сюда не включаем, поскольку он может находиться
    # в URL уже при первом открытии страницы.
    filters_submitted = any(
        parameter_name in request.query_params
        for parameter_name in (
            "year",
            "month",
            "review_place",
            "reviewed",
            "task_review_id",
        )
    )

    validation_error: str | None = None

    if (
        filters_submitted
        and selected_review_place is None
    ):
        validation_error = (
            "Для просмотра результатов необходимо "
            "выбрать место рассмотрения."
        )

    try:
        page_data = (
            await ReviewResultService.get_list_page_data(
                db,
                user=user,
                selected_school_id=selected_school_id,
                year=selected_year,
                month=selected_month,
                review_place=selected_review_place,
                reviewed=selected_reviewed,
                task_review_id=selected_task_review_id,
            )
        )

        context = {
            "user": user,
            **asdict(page_data),
        }

        if validation_error is not None:
            context["error"] = validation_error

        return render(
            templates,
            request,
            "reviews/review_results_list.html",
            ctx=context,
        )

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "reviews/review_results_list.html",
            ctx={
                "user": user,

                "school_plan_id": None,
                "school_id": selected_school_id,
                "academic_year_label": "Не указан",
                "is_admin": False,

                "selected_year": selected_year,
                "selected_month": selected_month,
                "selected_review_place": (
                    selected_review_place
                ),
                "selected_reviewed": selected_reviewed,
                "selected_task_review_id": (
                    selected_task_review_id
                ),

                "available_years": [],
                "available_months": [],
                "review_places": [
                    {
                        "value": str(
                            getattr(place, "value")
                        ),
                        "label": str(
                            getattr(place, "label_kz")
                        ),
                    }
                    for place in ReviewPlace
                ],
                "available_protocols": [],

                "items": [],

                "total_count": 0,
                "reviewed_count": 0,
                "not_reviewed_count": 0,
            },
            error=str(exc),
            status_code=400,
        )


# ==========================================================
# 2. Задача и история её рассмотрений
# ==========================================================
@router.get(
    "/tasks/{month_item_id}",
    name="review_result_task_detail_page",
)
async def review_result_task_detail_page(
        request: Request,
        month_item_id: int,

        school_id: str | None = Query(default=None),
        review_place: str | None = Query(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF)),
):
    """
    Показывает задачу и полную историю её рассмотрений.
    """

    selected_school_id = parse_optional_int(school_id)

    selected_review_place: ReviewPlace | None = None

    if review_place:
        normalized_review_place = review_place.strip()

        if normalized_review_place:
            try:
                selected_review_place = ReviewPlace(
                    normalized_review_place
                )
            except ValueError:
                selected_review_place = None

    try:
        page_data = (
            await ReviewResultService.get_task_detail_page_data(
                db,
                user=user,
                month_item_id=month_item_id,
                selected_school_id=selected_school_id,
                review_place=selected_review_place,
            )
        )

        return render(
            templates,
            request,
            "reviews/review_result_detail.html",
            ctx={
                "user": user,
                "detail": page_data,
                "school_id": selected_school_id,
                "selected_review_place": selected_review_place,
            },
        )

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "reviews/review_result_detail.html",
            ctx={
                "user": user,
                "detail": None,
                "school_id": selected_school_id,
                "selected_review_place": selected_review_place,
            },
            error=str(exc),
            status_code=404,
        )


# ==========================================================
# 3. Конкретный результат рассмотрения
# ==========================================================
@router.get(
    "/results/{review_result_id}",
    name="review_result_detail_page",
)
async def review_result_detail_page(
        request: Request,
        review_result_id: int,

        school_id: str | None = Query(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF)),
):
    """
    Показывает один конкретный результат рассмотрения.
    """

    selected_school_id = parse_optional_int(school_id)

    try:
        result = await ReviewResultService.get_result_detail(
            db,
            user=user,
            review_result_id=review_result_id,
            selected_school_id=selected_school_id,
        )

        target = request.url_for("review_result_task_detail_page", month_item_id=result.month_item_id)
        query = {"review_place": result.review_place}
        if selected_school_id is not None:
            query["school_id"] = selected_school_id
        target = target.include_query_params(**query)
        return RedirectResponse(str(target) + f"#review-result-{result.review_result_id}", status_code=303)

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "reviews/review_result_detail.html",
            ctx={
                "user": user,
                "result": None,
                "school_id": selected_school_id,
                "selected_review_place": None,
            },
            error=str(exc),
            status_code=404,
        )


# ==========================================================
# 4. Просмотр документа результата рассмотрения
# ==========================================================
@router.get(
    "/documents/{document_id}/view",
    name="review_result_document_view",
)
async def review_result_document_view(
        request: Request,
        document_id: int,

        school_id: str | None = Query(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF)),
):
    """
    Открывает документ результата рассмотрения.

    Доступ проверяется через ReviewResultService.
    Файл читается через выбранный backend хранилища
    (LocalStorage / S3 / MinIO).
    """
    selected_school_id = parse_optional_int(school_id)

    try:
        document = await ReviewResultService.get_document_for_access(
            db,
            user=user,
            document_id=document_id,
            selected_school_id=selected_school_id,
        )

        object_key = str(document.file_path or "").strip()

        if not object_key:
            raise ValueError(
                "У документа отсутствует путь к файлу."
            )

        storage = get_storage()

        if not await storage.exists(
            object_key=object_key,
        ):
            raise ValueError(
                "Файл документа не найден в хранилище."
            )

        download_url = await storage.get_download_url(
            object_key=object_key,
            expires_in=300,
        )

        return RedirectResponse(
            url=download_url,
            status_code=302,
        )

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "reviews/review_result_detail.html",
            ctx={
                "user": user,
                "detail": None,
                "result": None,
                "school_id": selected_school_id,
                "selected_review_place": None,
            },
            error=str(exc),
            status_code=404,
        )


# ==========================================================
# 5. Скачивание документа результата рассмотрения
# ==========================================================
@router.get(
    "/documents/{document_id}/download",
    name="review_result_document_download",
)
async def review_result_document_download(
        request: Request,
        document_id: int,

        school_id: str | None = Query(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN, UserRole.SCHOOL_STAFF)),
):
    """
    Скачивает документ результата рассмотрения.

    Доступ проверяется через ReviewResultService.
    Файл читается через выбранный backend хранилища
    (LocalStorage / S3 / MinIO).
    """
    selected_school_id = parse_optional_int(school_id)

    try:
        document = await ReviewResultService.get_document_for_access(
            db,
            user=user,
            document_id=document_id,
            selected_school_id=selected_school_id,
        )

        object_key = str(document.file_path or "").strip()

        if not object_key:
            raise ValueError(
                "У документа отсутствует путь к файлу."
            )

        storage = get_storage()

        if not await storage.exists(
            object_key=object_key,
        ):
            raise ValueError(
                "Файл документа не найден в хранилище."
            )

        download_url = await storage.get_download_url(
            object_key=object_key,
            expires_in=300,
        )

        return RedirectResponse(
            url=download_url,
            status_code=302,
        )

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "reviews/review_result_detail.html",
            ctx={
                "user": user,
                "detail": None,
                "result": None,
                "school_id": selected_school_id,
                "selected_review_place": None,
            },
            error=str(exc),
            status_code=404,
        )
