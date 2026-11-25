# app/routers/web/planning/month_plan_web.py

from __future__ import annotations

from app.core.i18n import resolve_language
from app.modules.planning.utils.month_plan_readiness import month_plan_readiness

from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.org.models import School
from starlette import status
from starlette.responses import HTMLResponse, RedirectResponse

from app.db.session import get_db
from app.modules.planning.repositories.month_correction_repo import MonthCorrectionRepo
from app.modules.planning.services.month_correction_service import MonthCorrectionService
from app.modules.planning.constants import ACADEMIC_MONTHS, MONTH_LABELS
from app.modules.planning.enums import PlanStatus
from app.modules.planning.repositories.month_plan_repository import (
    SchoolMonthlyPlanRepo,
)
from app.modules.planning.schemas.month_plan_inputs import MonthItemUpdate
from app.modules.planning.services.month_plan_notification_service import MonthPlanNotificationService
from app.modules.planning.services.month_plan_service import (
    SchoolMonthlyPlanningService,
)
from app.modules.staff.utils.staff_require_school import require_school_id
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates
from app.utils.calendar_weeks import (
    calc_year_from_academic,
    month_weeks_grid,
)

router = APIRouter(
    prefix="/planning/school",
    tags=["planning-school-month-plan"],
)


def _months_list() -> list[dict[str, Any]]:
    return [
        {
            "num": month,
            "label": MONTH_LABELS.get(month, str(month)),
        }
        for month in ACADEMIC_MONTHS
    ]


'''
def _group_items_by_direction(items) -> list[dict[str, Any]]:
    """
    Сгруппировать строки месячного плана по направлению.

    Репозиторий должен заранее загрузить:
    - item.source_row11;
    - item.source_row11.direction.
    """

    grouped: dict[int, dict[str, Any]] = {}

    for item in items:
        source_row = getattr(item, "source_row11", None)
        direction = (
            getattr(source_row, "direction", None)
            if source_row is not None
            else None
        )
        direction_id = (
                           getattr(source_row, "direction_id", None)
                           if source_row is not None
                           else None
                       ) or 0

        group = grouped.setdefault(
            direction_id,
            {
                "direction_id": direction_id,
                "direction": direction,
                "items": [],
            },
        )
        group["items"].append(item)

    def sort_key(
            direction_group: dict[str, Any],
    ) -> tuple[int, int]:

        group_direction = direction_group.get(
            "direction"
        )

        if group_direction is None:
            return (
                9999,
                direction_group.get(
                    "direction_id",
                    0,
                ),
            )

        sort_order = getattr(
            group_direction,
            "sort_order",
            None,
        )

        group_direction_id = getattr(
            group_direction,
            "id",
            0,
        )

        return (
            sort_order
            if sort_order is not None
            else 9999,
            group_direction_id,
        )

    return sorted(grouped.values(), key=sort_key)
'''


def _month_page_redirect(
        request: Request,
        *,
        month: int,
        success: str | None = None,
        warning: str | None = None,
        info: str | None = None,
        reset_form: bool = False,
        submission_failed: bool = False,
) -> RedirectResponse:
    query: dict[str, str | int] = {"month": month}
    if submission_failed:
        query["submission_failed"] = 1
    if reset_form:
        query["reset_form"] = 1

    if success:
        query["success"] = success
    if warning:
        query["warning"] = warning
    if info:
        query["info"] = info

    base_url = request.url_for("school_monthly_page")

    return RedirectResponse(
        url=f"{base_url}?{urlencode(query)}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


def _validate_academic_month(month: int) -> None:
    if month not in ACADEMIC_MONTHS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый месяц учебного года.",
        )


@router.get(
    "/monthly",
    name="school_monthly_page",
    response_class=HTMLResponse,
)
async def school_monthly_page(
        request: Request,
        month: int | None = Query(default=None),
        success: str | None = Query(default=None),
        warning: str | None = Query(default=None),
        info: str | None = Query(default=None),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    school_id = getattr(user, "school_id", None)

    if school_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У пользователя не задана школа.",
        )

    months = _months_list()

    active_plan = (
        await SchoolMonthlyPlanRepo
        .get_active_school_plan(
            db,
            school_id=school_id,
        )
    )

    base_context = {
        "user": user,
        "months": months,
        "month": month,
        "active_plan": active_plan,
        "month_plan": None,
        "school_plan_id": (
            active_plan.id
            if active_plan is not None
            else None
        ),
        "blocks": [],
        "weeks": [],
        "can_build": False,
        "open_month_plan_id": None,
        "success": success,
        "warning": warning,
        "info": info,
        "PlanStatus": PlanStatus,
    }

    if active_plan is None:
        base_context["error"] = (
            "Нет активного годового плана. "
            "Сначала активируйте годовой план."
        )

        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            base_context,
        )

    if month is None:
        base_context["info"] = (
                info
                or "Выберите месяц и нажмите «Открыть план»."
        )

        return render(
            templates,
            request,
            "planning/school/monthly_tasks.html",
            base_context,
        )

    _validate_academic_month(month)

    year = calc_year_from_academic(
        active_plan.academic_year,
        month,
    )

    month_plan = (
        await SchoolMonthlyPlanRepo
        .get_month_plan(
            db,
            school_plan_id=active_plan.id,
            year=year,
            month=month,
        )
    )

    assignment_data = (await MonthCorrectionRepo.snapshot(db, school_id=school_id, month_plan_id=month_plan.id)) if month_plan else None
    blocks = []

    if month_plan is not None:
        blocks = (
            await SchoolMonthlyPlanningService
            .build_month_plan_direction_blocks(
                db,
                month_plan_id=month_plan.id,
                schedule_data=assignment_data,
            )
        )

    assignment_editors, plan_revision = MonthCorrectionService.editor(assignment_data)
    base_context.update(assignment_editors=assignment_editors, plan_revision=plan_revision)
    base_context['monthly_state'] = month_plan_readiness(assignment_data, month_weeks_grid(year, month))
    visible_ids={item.id for block in blocks for item in block.items}
    base_context['monthly_state']['unpublished']=[i for i in base_context['monthly_state']['unpublished'] if i in visible_ids]
    base_context['schedule_hidden_count']=len(assignment_data['items'])-len(visible_ids) if assignment_data else 0
    base_context['problem_topics'] = {item.id: item.topic for block in blocks for item in block.items}
    saved_id = request.query_params.get('task_saved', '')
    base_context['saved_task'] = next((dict(item) for item in assignment_data['items'] if str(item['id']) == saved_id), None) if assignment_data else None

    base_context['submission_failed'] = (request.query_params.get('submission_failed') == '1'
        or bool(warning and ('Проблемные item_id' in warning or warning.startswith('У всех включённых задач'))))


    base_context.update(
        {
            "month_plan": month_plan,
            "blocks": blocks,
            "weeks": month_weeks_grid(
                year,
                month,
            ),
            "can_build": month_plan is None,
            "open_month_plan_id": (
                month_plan.id
                if month_plan is not None
                else None
            ),
        }
    )

    return render(
        templates,
        request,
        "planning/school/monthly_tasks.html",
        base_context,
    )


@router.post(
    "/monthly/{month}/draft",
    name="school_monthly_build_draft",
)
async def school_monthly_build_draft(
        request: Request,
        month: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    school_id = getattr(user, "school_id", None)

    if school_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У пользователя не задана школа.",
        )

    _validate_academic_month(month)

    try:
        active_plan = (
            await SchoolMonthlyPlanRepo.get_active_school_plan(
                db,
                school_id=school_id,
            )
        )

        if active_plan is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Нет активного годового плана.",
            )

        year = calc_year_from_academic(
            active_plan.academic_year,
            month,
        )

        await SchoolMonthlyPlanningService.get_or_create_draft(
            db,
            school_id=school_id,
            school_plan_id=active_plan.id,
            year=year,
            month=month,
        )

        await db.commit()

    except HTTPException as exc:
        await db.rollback()
        return _month_page_redirect(
            request,
            month=month,
            warning=str(exc.detail),
        )
    except Exception:
        await db.rollback()
        raise

    return _month_page_redirect(
        request,
        month=month,
        success=("Состав задач обновлён. Сохранённые назначения и результаты сохранены." if resolve_language(request,user)=="ru" else "Тапсырмалар құрамы жаңартылды. Сақталған тағайындаулар мен нәтижелер сақталды."),
    )


@router.post(
    "/monthly/{month}/save",
    name="school_monthly_save_draft",
)
async def school_monthly_save_draft(
        request: Request,
        month: int,
        month_plan_id: int = Form(...),
        school_plan_id: int = Form(...),
        item_ids: list[int] = Form(default=[]),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    school_id = getattr(user, "school_id", None)

    if school_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У пользователя не задана школа.",
        )

    _validate_academic_month(month)

    submitted_form = await request.form()
    publishing = submitted_form.get("intent") == "submit"
    try:
        school_plan = (
            await SchoolMonthlyPlanRepo.get_school_plan_for_school(
                db,
                school_plan_id=school_plan_id,
                school_id=school_id,
            )
        )

        if school_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "Годовой план не найден "
                    "или не принадлежит школе."
                ),
            )

        month_plan = (
            await SchoolMonthlyPlanRepo
            .get_month_plan_for_school_by_id(
                db,
                month_plan_id=month_plan_id,
                school_id=school_id,
            )
        )

        if month_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Месячный план не найден.",
            )

        if (
                month_plan.school_plan_id != school_plan_id
                or month_plan.month != month
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Месячный план не соответствует "
                    "годовому плану или выбранному месяцу."
                ),
            )
        # =====================================================
        # ARCHIVE GUARD
        # =====================================================

        school_plan_status = (
            school_plan.status.value
            if hasattr(school_plan.status, "value")
            else str(school_plan.status)
        )

        if school_plan_status == PlanStatus.ARCHIVED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Мұрағатталған оқу жылының "
                    "айлық жоспарын өзгертуге болмайды."
                ),
            )

        if month_plan.status == PlanStatus.ARCHIVED:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "Мұрағатталған айлық жоспарды "
                    "өзгертуге болмайды."
                ),
            )

        existing_items = await SchoolMonthlyPlanRepo.list_items(
            db,
            month_plan_id=month_plan_id,
            with_source=False,
        )
        allowed_item_ids = {
            item.id
            for item in existing_items
        }

        normalized_item_ids = list(dict.fromkeys(item_ids))

        invalid_item_ids = (
                set(normalized_item_ids)
                - allowed_item_ids
        )

        if invalid_item_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Форма содержит строки, которые не относятся "
                    "к выбранному месячному плану."
                ),
            )

        form = await request.form()
        weeks = month_weeks_grid(
            month_plan.year,
            month_plan.month,
        )
        week_map = {
            week.week: week
            for week in weeks
        }

        updates: list[MonthItemUpdate] = []

        for item_id in normalized_item_ids:
            is_included = (
                    form.get(f"item_{item_id}_included")
                    == "1"
            )

            week_raw = str(
                form.get(f"item_{item_id}_week")
                or ""
            ).strip()

            week_of_month = (
                int(week_raw)
                if week_raw.isdigit()
                else None
            )

            planned_start = None
            planned_end = None

            if week_of_month is not None:
                week = week_map.get(week_of_month)

                if week is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Неделя {week_of_month} отсутствует "
                            f"в календаре месяца. item_id={item_id}"
                        ),
                    )

                planned_start = week.start
                planned_end = week.end

            notes = str(
                form.get(f"item_{item_id}_notes")
                or ""
            ).strip() or None

            updates.append(
                MonthItemUpdate(
                    item_id=item_id,
                    is_included=is_included,
                    week_of_month=week_of_month,
                    planned_start=planned_start,
                    planned_end=planned_end,
                    notes=notes,
                )
            )

        audit = await MonthCorrectionService.save(
            db, school_id=school_id, month_plan_id=month_plan_id,
            school_plan_id=school_plan_id, month=month, updates=updates,
            form=form, actor_id=user.id,
        )
        if publishing:
            await SchoolMonthlyPlanningService.submit_month_plan(
                db, month_plan_id=month_plan_id, school_id=school_id)
        await db.commit()
        MonthCorrectionService.log_committed(audit)

    except HTTPException as exc:
        await db.rollback()
        return _month_page_redirect(
            request,
            month=month,
            warning=str(exc.detail),
            reset_form=(exc.status_code == 409),
            submission_failed=publishing,
        )
    except Exception:
        await db.rollback()
        raise

    return _month_page_redirect(
        request,
        month=month,
        success=("План отправлен на исполнение / Жоспар орындауға жіберілді" if publishing else "Месячный план и назначения сохранены / Айлық жоспар мен тағайындаулар сақталды."),
    )


@router.post(
    "/monthly/{month}/submit",
    name="school_monthly_submit",
)
async def school_monthly_submit(
        request: Request,
        month: int,
        month_plan_id: int = Form(...),
        school_plan_id: int = Form(...),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    school_id = getattr(user, "school_id", None)

    if school_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У пользователя не задана школа.",
        )

    _validate_academic_month(month)

    try:
        month_plan = (
            await SchoolMonthlyPlanRepo
            .get_month_plan_for_school_by_id(
                db,
                month_plan_id=month_plan_id,
                school_id=school_id,
            )
        )

        if month_plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Месячный план не найден.",
            )

        if (
                month_plan.school_plan_id != school_plan_id
                or month_plan.month != month
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Месячный план не соответствует "
                    "переданным параметрам."
                ),
            )

        await SchoolMonthlyPlanningService.submit_month_plan(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )

        await db.commit()

    except HTTPException as exc:
        await db.rollback()

        return _month_page_redirect(
            request,
            month=month,
            warning=str(exc.detail),
            submission_failed=True,
        )

    except Exception:
        await db.rollback()
        raise

    return _month_page_redirect(request, month=month,
        success="План отправлен на исполнение / Жоспар орындауға жіберілді")


@router.post(
    "/monthly/delete",
    name="school_monthly_delete_draft",
)
async def school_monthly_delete_draft(
        request: Request,
        month_plan_id: int = Form(...),
        month: int = Form(...),
        plan_revision: str = Form(default=""),
        confirmed_plan_id: str = Form(default=""),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    school_id = getattr(user, "school_id", None)

    if school_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="У пользователя не задана школа.",
        )

    _validate_academic_month(month)

    try:
        await (
            SchoolMonthlyPlanningService
            .delete_draft_month_plan(
                db,
                month_plan_id=month_plan_id,
                school_id=school_id,
                plan_revision=plan_revision, confirmed_plan_id=confirmed_plan_id,
            )
        )
        await db.commit()

    except HTTPException as exc:
        await db.rollback()
        return _month_page_redirect(
            request,
            month=month,
            warning=str(exc.detail),
        )
    except Exception:
        await db.rollback()
        raise

    return _month_page_redirect(
        request,
        month=month,
        info="Черновик месячного плана удалён.",
    )


@router.get(
    "/monthly/{month_plan_id}/notifications",
    name="school_monthly_notifications",
    response_class=HTMLResponse,
)
async def school_monthly_notifications(
    request: Request,
    month_plan_id: int,
    error: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.SCHOOL_ADMIN)
    ),
):
    """
    Показать получателей и текущее состояние
    уведомлений месячного плана.
    """

    school_id = require_school_id(user)

    month_plan = await (
        SchoolMonthlyPlanRepo.get_month_plan_for_school_by_id(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )
    )

    if month_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Месячный план не найден.",
        )

    recipients = await (
        MonthPlanNotificationService.list_recipients(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )
    )

    notification_statuses = await (
        MonthPlanNotificationService.list_notification_statuses(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )
    )

    notification_status_map = {
        item.staff_member_id: item
        for item in notification_statuses
    }

    internal_rows = await MonthPlanNotificationService.internal_statuses(db, school_id=school_id, month_plan_id=month_plan_id, recipients=recipients)

    return render(
        templates,
        request,
        "planning/school/month_plan_notifications.html",
        {
            "user": user,
            "month_plan": month_plan,
            "month_plan_id": month_plan_id,
            "recipients": recipients,
            "notification_statuses": notification_statuses,
            "notification_status_map": notification_status_map,
            "internal_summary": MonthPlanNotificationService.internal_summary(recipients,internal_rows),
            "whatsapp_opened": sum(row.open_count > 0 for row in notification_statuses),
            "error": error,
            "internal_status_map": {row['staff_member_id']: row for row in internal_rows},
            "internal_success": request.query_params.get('internal_success'),
        },
    )


@router.get(
    (
            "/monthly/{month_plan_id}/notifications/"
            "{staff_member_id}/whatsapp"
    ),
    name="school_monthly_whatsapp",
)
async def school_monthly_whatsapp(
        request: Request,
        month_plan_id: int,
        staff_member_id: int,
        phone: str = Query(..., min_length=1),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.SCHOOL_ADMIN)
        ),
):
    """
    Сформировать персональное WhatsApp-сообщение,
    зафиксировать открытие и перенаправить администратора
    на ссылку wa.me.
    """

    school_id = require_school_id(user)

    month_plan = await (
        SchoolMonthlyPlanRepo.get_month_plan_for_school_by_id(
            db,
            month_plan_id=month_plan_id,
            school_id=school_id,
        )
    )

    if month_plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Месячный план не найден.",
        )

    platform_url = str(request.base_url).rstrip("/")

    try:
        # Do not access user.school: an unloaded async ORM relationship would
        # perform implicit I/O outside greenlet_spawn (MissingGreenlet).
        school_name = await db.scalar(
            select(School.name).where(School.id == school_id)
        )

        whatsapp_url = await (
            MonthPlanNotificationService.open_recipient_whatsapp(
                db,
                month_plan_id=month_plan_id,
                school_id=school_id,
                staff_member_id=staff_member_id,
                phone=phone,
                platform_url=platform_url,
                opened_by_user_id=user.id,
                school_name=school_name,
                language=resolve_language(request, user),
            )
        )

        await db.commit()

    except HTTPException:
        await db.rollback()
        raise

    except Exception:
        await db.rollback()
        raise

    return RedirectResponse(
        url=whatsapp_url,
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post('/monthly/review-places/sync', name='school_monthly_sync_review_places')
async def school_monthly_sync_review_places(
    request: Request,
    month_plan_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN)),
):
    from app.modules.planning.services.review_place_sync_service import ReviewPlaceSyncService
    try:
        context, stats = await ReviewPlaceSyncService.sync_month(db, school_id=require_school_id(user), month_plan_id=month_plan_id)
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    import logging
    logging.getLogger(__name__).info('MONTH_REVIEW_PLACES_SYNC actor=%s plan=%s stats=%s', user.id, month_plan_id, stats)
    query = dict(month=context['month'], school_plan_id=context['school_plan_id'], restore_plan_draft=1,
        success=f"Места рассмотрения обновлены. Задач: {stats['updated']}. / Қарау орындары жаңартылды. Тапсырмалар: {stats['updated']}.")
    if stats['unrecognized']:
        query['warning'] = f"Проверьте место рассмотрения в годовом плане: не распознано задач {stats['unrecognized']}. / Жылдық жоспардағы қарау орнын тексеріңіз: {stats['unrecognized']}."
    return RedirectResponse(str(request.url_for('school_monthly_page')) + '?' + urlencode(query), status_code=303)


@router.post('/monthly/{month_plan_id}/notifications/internal', name='school_monthly_notify_internal')
async def school_monthly_notify_internal(request: Request, month_plan_id: int,
        db: AsyncSession = Depends(get_db), user: User = Depends(require_roles(UserRole.SCHOOL_ADMIN))):
    school_id = require_school_id(user)
    try:
        result = await MonthPlanNotificationService.send_internal(db,school_id=school_id,
            month_plan_id=month_plan_id,actor_id=user.id)
        await db.commit()
    except HTTPException as exc:
        await db.rollback()
        return RedirectResponse(str(request.url_for('school_monthly_notifications',month_plan_id=month_plan_id))+'?'+urlencode({'error':str(exc.detail)}),status_code=303)
    except Exception:
        await db.rollback()
        raise
    ru = resolve_language(request,user) == 'ru'
    message = (f"Создано: {result['created']}. Обновлено: {result['changed']}. Без изменений: {result['unchanged']}. Нет активной учётной записи: {result['unregistered']}." if ru else
        f"Жасалды: {result['created']}. Жаңартылды: {result['changed']}. Өзгеріссіз: {result['unchanged']}. Белсенді тіркелгісі жоқ: {result['unregistered']}.")
    return RedirectResponse(str(request.url_for('school_monthly_notifications',month_plan_id=month_plan_id))+'?'+urlencode({'internal_success':message}),status_code=303)
