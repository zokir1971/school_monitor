# app/routers/web/tasks/task_review_web.py

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import logging
from typing import cast
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.planning.enums import ReviewPlace
from app.modules.reviews.task_review_dto import TaskReviewBatchCreateDTO
from app.modules.reviews.services.task_review_service import TaskReviewService
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render, render_error
from app.routers.web.web_common import templates

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/staff/tasks",
    tags=["Staff task reviews"],
)


def _selection_url(
        request: Request,
        *,
        review_place: ReviewPlace,
        method_association_id: int | None = None,
        **extra_query_params,
) -> str:
    """Формирует URL возврата на страницу рассмотрения."""

    query_params: dict[str, object] = {
        "review_place": review_place.value,
    }

    if method_association_id is not None:
        query_params["method_association_id"] = method_association_id

    for key, value in extra_query_params.items():
        if value is not None:
            query_params[key] = value

    base_url = request.url_for("task_review_selection_page")
    query_string = urlencode(query_params, doseq=True)

    return f"{base_url}?{query_string}"


def _empty_page_context(
        *,
        user: User,
        review_place: ReviewPlace | None,
        school_plan_id: int | None = None,
        month_item_ids: list[int] | None = None,
        method_association_id: int | None = None,
        protocol_number: str = "",
        protocol_date: str = "",
        comment: str = "",
) -> dict:
    """Создаёт безопасный контекст для отображения ошибки."""

    return {
        "user": user,
        "school_plan_id": school_plan_id,
        "academic_year_label": "",
        "selected_review_place": review_place,
        "selected_method_association_id": method_association_id,
        "selected_method_association_label": "",
        "selected_place_label": "",
        "review_places": list(ReviewPlace),
        "method_associations": [],
        "tasks": [],
        "overdue_tasks": [],
        "form_data": {
            "review_place": (
                review_place.value
                if review_place is not None
                else ""
            ),
            "month_item_ids": month_item_ids or [],
            "method_association_id": method_association_id,
            "protocol_number": protocol_number,
            "protocol_date": protocol_date,
            "comment": comment,
        },
    }


@router.get(
    "/reviews",
    name="task_review_selection_page",
    response_class=HTMLResponse,
)
async def task_review_selection_page(
        request: Request,
        review_place: ReviewPlace | None = Query(default=None),
        method_association_id: int | None = Query(default=None, ge=1),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    """Отображает страницу пакетного рассмотрения задач."""

    try:
        page_data = await TaskReviewService.get_review_selection_page_data(
            db,
            user=user,
            review_place=review_place,
            method_association_id=method_association_id,
        )

        return render(templates, request,
            "reviews/task_review.html",
            {
                "request": request,
                "user": user,
                **asdict(page_data),
                "form_data": {
                    "review_place": (
                        review_place.value
                        if review_place is not None
                        else ""
                    ),
                    "month_item_ids": [],
                    "method_association_id": method_association_id,
                    "protocol_number": "",
                    "protocol_date": "",
                    "comment": "",
                },
            },
        )

    except ValueError as exc:
        return render_error(
            templates,
            request,
            "reviews/task_review.html",
            _empty_page_context(
                user=user,
                review_place=review_place,
                method_association_id=method_association_id,
            ),
            error=str(exc),
            status_code=400,
        )


@router.post(
    "/reviews",
    name="staff_task_review_batch",
)
async def staff_task_review_batch(
        request: Request,
        school_plan_id: int = Form(..., ge=1),
        review_place: ReviewPlace = Form(...),
        method_association_id: int | None = Form(default=None),
        protocol_number: str = Form(..., min_length=1, max_length=100),
        protocol_date: date = Form(...),
        protocol_file: UploadFile = File(...),
        comment: str | None = Form(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    """
    Атомарно сохраняет пакетное рассмотрение задач и протокол.

    Один HTTP-запрос соответствует одной бизнес-операции:
    протокол и результаты задач фиксируются одним commit.
    """

    pending_file_keys: list[str] = []
    committed = False
    form = await request.form()
    raw_month_item_ids = form.getlist("month_item_ids")

    try:
        unique_month_item_ids = list(
            dict.fromkeys(
                int(value)
                for value in raw_month_item_ids
                if str(value).strip()
            )
        )
    except (TypeError, ValueError):
        unique_month_item_ids = []

    normalized_protocol_number = protocol_number.strip()
    normalized_comment = (
        comment.strip()
        if comment and comment.strip()
        else None
    )

    try:
        if not unique_month_item_ids:
            raise ValueError(
                "Необходимо выбрать хотя бы одну задачу."
            )

        if not normalized_protocol_number:
            raise ValueError(
                "Необходимо указать номер протокола."
            )

        dto = TaskReviewBatchCreateDTO(
            month_item_ids=unique_month_item_ids,
            review_place=review_place,
            reviewed_by_user_id=cast(int, user.id),
            protocol_number=normalized_protocol_number,
            protocol_date=protocol_date,
            method_association_id=method_association_id,
            comment=normalized_comment,
        )

        review_results = await TaskReviewService.review_tasks_batch(
            db,
            dto=dto,
            school_plan_id=school_plan_id,
            protocol_file=protocol_file,
            user=user,
            pending_file_keys=pending_file_keys,
        )

        await db.commit()
        committed = True

        return RedirectResponse(
            url=_selection_url(
                request,
                review_place=review_place,
                method_association_id=method_association_id,
                success="reviewed",
                reviewed_count=len(review_results),
            ),
            status_code=303,
        )

    except ValueError as exc:
        if db.in_transaction():
            await db.rollback()
            await db.refresh(user)

        try:
            page_data = await TaskReviewService.get_review_selection_page_data(
                db,
                user=user,
                review_place=review_place,
                method_association_id=method_association_id,
            )

            context = {
                "request": request,
                "user": user,
                **asdict(page_data),
                "form_data": {
                    "month_item_ids": unique_month_item_ids,
                    "review_place": review_place.value,
                    "method_association_id": method_association_id,
                    "protocol_number": normalized_protocol_number,
                    "protocol_date": protocol_date.isoformat(),
                    "comment": comment or "",
                },
            }

        except ValueError as page_exc:
            context = _empty_page_context(
                user=user,
                review_place=review_place,
                school_plan_id=school_plan_id,
                month_item_ids=unique_month_item_ids,
                method_association_id=method_association_id,
                protocol_number=normalized_protocol_number,
                protocol_date=protocol_date.isoformat(),
                comment=comment or "",
            )

            exc = ValueError(
                f"{exc} Дополнительно: {page_exc}"
            )

        return render_error(
            templates,
            request,
            "reviews/task_review.html",
            context,
            error=str(exc),
            status_code=400,
        )

    except OSError:
        if db.in_transaction():
            await db.rollback()
            await db.refresh(user)

        logger.exception(
            "Ошибка файлового хранилища при сохранении рассмотрения."
        )

        try:
            page_data = await TaskReviewService.get_review_selection_page_data(
                db,
                user=user,
                review_place=review_place,
                method_association_id=method_association_id,
            )
            context = {
                "request": request,
                "user": user,
                **asdict(page_data),
                "form_data": {
                    "month_item_ids": unique_month_item_ids,
                    "review_place": review_place.value,
                    "method_association_id": method_association_id,
                    "protocol_number": normalized_protocol_number,
                    "protocol_date": protocol_date.isoformat(),
                    "comment": comment or "",
                },
            }
        except ValueError:
            context = _empty_page_context(
                user=user,
                review_place=review_place,
                school_plan_id=school_plan_id,
                month_item_ids=unique_month_item_ids,
                method_association_id=method_association_id,
                protocol_number=normalized_protocol_number,
                protocol_date=protocol_date.isoformat(),
                comment=comment or "",
            )

        return render_error(
            templates,
            request,
            "reviews/task_review.html",
            context,
            error=(
                "Не удалось сохранить файл протокола. "
                "Повторите попытку."
            ),
            status_code=500,
        )

    except SQLAlchemyError:
        if db.in_transaction():
            await db.rollback()

        logger.exception(
            "Ошибка БД при пакетном рассмотрении задач."
        )
        raise

    finally:
        if not committed:
            for object_key in pending_file_keys:
                await TaskReviewService.cleanup_protocol_file(object_key)
        await protocol_file.close()


@router.post(
    "/reviews/mark-overdue",
    name="staff_task_review_mark_overdue",
)
async def staff_task_review_mark_overdue(
        request: Request,
        school_plan_id: int = Form(..., ge=1),
        review_place: ReviewPlace = Form(...),
        method_association_id: int | None = Form(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    """Переводит выбранные просроченные задачи в NOT_EXECUTED."""

    form = await request.form()
    raw_month_item_ids = form.getlist("month_item_ids")

    try:
        unique_ids = list(
            dict.fromkeys(
                int(value)
                for value in raw_month_item_ids
                if str(value).strip()
            )
        )
    except (TypeError, ValueError):
        unique_ids = []

    try:
        if not unique_ids:
            raise ValueError(
                "Выберите хотя бы одну просроченную задачу."
            )

        updated_count = await TaskReviewService.mark_overdue_tasks_not_executed(
            db,
            month_item_ids=unique_ids,
            school_plan_id=school_plan_id,
            user=user,
            review_place=review_place,
            method_association_id=method_association_id,
        )

        await db.commit()

        return RedirectResponse(
            url=_selection_url(
                request,
                review_place=review_place,
                method_association_id=method_association_id,
                success="marked_not_executed",
                updated_count=updated_count,
            ),
            status_code=303,
        )

    except ValueError as exc:
        if db.in_transaction():
            await db.rollback()

        return RedirectResponse(
            url=_selection_url(
                request,
                review_place=review_place,
                method_association_id=method_association_id,
                error=str(exc),
            ),
            status_code=303,
        )

    except SQLAlchemyError:
        if db.in_transaction():
            await db.rollback()

        logger.exception(
            "Ошибка БД при переводе просроченных задач в NOT_EXECUTED."
        )
        raise
