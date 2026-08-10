# app/modules/reviews/routes/review_result_routes.py

from __future__ import annotations

import mimetypes
from dataclasses import asdict
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import FileResponse

from app.db.session import get_db
from app.modules.planning.enums import ReviewPlace
from app.modules.reviews.services.review_result_service import (
    ReviewResultService,
)
from app.modules.users.deps import (
    require_school_member_scope,
)
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

PROJECT_ROOT = Path(__file__).resolve().parents[4]
STORAGE_ROOT = PROJECT_ROOT / "storage"


def _resolve_review_document_path(
        stored_file_path: str,
) -> Path:
    """
    Преобразует путь из БД в абсолютный путь файла.

    В БД:
        schools/region-1/...

    На диске:
        <project>/storage/schools/region-1/...
    """

    relative_path = Path(
        stored_file_path.replace("\\", "/")
    )

    if relative_path.is_absolute():
        resolved_path = relative_path.resolve()
    else:
        resolved_path = (
                STORAGE_ROOT / relative_path
        ).resolve()

    storage_root_resolved = STORAGE_ROOT.resolve()

    try:
        resolved_path.relative_to(storage_root_resolved)
    except ValueError as exc:
        raise ValueError(
            "Некорректный путь документа."
        ) from exc

    return resolved_path


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
    user: User = Depends(require_school_member_scope),
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
        user: User = Depends(require_school_member_scope),
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
        user: User = Depends(require_school_member_scope),
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

        return render(
            templates,
            request,
            "reviews/review_result_detail.html",
            ctx={
                "user": user,
                "result": result,
                "school_id": selected_school_id,
                "selected_review_place": None,
            },
        )

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
        user: User = Depends(require_school_member_scope),
):
    """
        Открывает документ в браузере.

        Доступ проверяется через ReviewResultService.
        Клиент передаёт только идентификатор документа.
        """
    selected_school_id = parse_optional_int(school_id)

    try:
        document = await ReviewResultService.get_document_for_access(
            db,
            user=user,
            document_id=document_id,
            selected_school_id=selected_school_id,
        )

        file_path = _resolve_review_document_path(
            document.file_path
        )

        if not file_path.is_file():
            raise ValueError(
                "Файл документа не найден."
            )

        media_type, _ = mimetypes.guess_type(
            str(file_path)
        )

        return FileResponse(
            path=file_path,
            media_type=media_type or "application/octet-stream",
            filename=document.file_name or file_path.name,
            content_disposition_type="inline",
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
        user: User = Depends(require_school_member_scope),
):
    """
        Скачивает документ результата рассмотрения.

        Доступ проверяется через ReviewResultService.
        """
    selected_school_id = parse_optional_int(school_id)

    try:
        document = await ReviewResultService.get_document_for_access(
            db,
            user=user,
            document_id=document_id,
            selected_school_id=selected_school_id,
        )

        file_path = _resolve_review_document_path(
            document.file_path
        )

        if not file_path.is_file():
            raise ValueError(
                "Файл документа не найден."
            )

        media_type, _ = mimetypes.guess_type(
            str(file_path)
        )

        return FileResponse(
            path=file_path,
            media_type=media_type or "application/octet-stream",
            filename=document.file_name or file_path.name,
            content_disposition_type="inline",
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
