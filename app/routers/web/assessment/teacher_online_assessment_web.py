# app/routers/web/assessment/teacher_online_assessment_web.py

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.modules.assessment.services.assessment_manual_grading_service import (
    AssessmentManualGradingService,
)
from app.modules.assessment.services.teacher_assessment_result_service import (
    TeacherAssessmentResultService,
)
from app.modules.assessment.services.teacher_online_assessment_service import TeacherOnlineAssessmentService
from app.modules.staff.utils.staff_require_member import (
    require_staff_member_id,
)
from app.modules.staff.utils.staff_require_school import (
    require_school_id,
)
from app.modules.users.deps import (
    require_teacher_workspace,
)
from app.modules.users.models import User
from app.routers.web.helpers.render import (
    render, render_error,
)
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/teacher/assessment/online",
    tags=["teacher-online-assessment"],
)


# =========================================================
# HELPERS
# =========================================================


def _parse_score(
        value: object | None,
) -> Decimal:
    """
    Преобразовать значение score из HTML-формы в Decimal.

    Поддерживает:
        1
        1.5
        1,5

    Проверка диапазона:
        0 <= score <= max_score

    выполняется в AssessmentManualGradingService.
    """

    raw = (
        ""
        if value is None
        else str(value).strip()
    )

    if not raw:
        raise ValueError(
            "Баллды енгізіңіз."
        )

    raw = raw.replace(
        ",",
        ".",
    )

    try:
        score = Decimal(
            raw
        )

    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ValueError(
            "Балл дұрыс сан болуы керек."
        ) from exc

    if not score.is_finite():
        raise ValueError(
            "Балл шекті сан болуы керек."
        )

    return score


# =========================================================
# ONLINE ASSESSMENTS
# =========================================================


@router.get(
    "",
    name="teacher_online_assessment_list_page",
    response_class=HTMLResponse,
)
async def teacher_online_assessment_list_page(
        request: Request,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Рабочая страница ONLINE Assessment учителя.

    Показывает только ONLINE Assessment,
    назначенные группам текущего учителя.

    Security boundary:
        school_id
        teacher_staff_member_id

    Repository выполняет teacher boundary
    и агрегирует состояния участников.
    """

    # =====================================================
    # SECURITY BOUNDARY
    # =====================================================

    school_id = require_school_id(
        user
    )

    teacher_staff_member_id = (
        require_staff_member_id(
            user
        )
    )

    # =====================================================
    # PAGE DATA
    # =====================================================

    page_data = (
        await TeacherOnlineAssessmentService
        .get_list_page(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
        )
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/online/list.html",
        {
            "user": user,

            "dto": page_data,

            "items": (
                page_data.items
            ),

            "total_assessments": (
                page_data.total_assessments
            ),

            "total_students": (
                page_data.total_students
            ),

            "assigned_count": (
                page_data.assigned_count
            ),

            "in_progress_count": (
                page_data.in_progress_count
            ),

            "pending_review_count": (
                page_data.pending_review_count
            ),

            "completed_count": (
                page_data.completed_count
            ),

            "assessments_with_pending_review_count": (
                page_data
                .assessments_with_pending_review_count
            ),

            "has_pending_review": (
                page_data.has_pending_review
            ),
        },
    )


# =========================================================
# ONLINE ASSESSMENT -> GROUPS
# =========================================================


@router.get(
    "/{assessment_id}/groups",
    name="teacher_online_assessment_groups_page",
    response_class=HTMLResponse,
)
async def teacher_online_assessment_groups_page(
        request: Request,
        assessment_id: int,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Страница групп конкретного ONLINE Assessment
    текущего учителя.

    Показывает только группы Assessment,
    назначенные текущему учителю.

    Security boundary:
        school_id
        teacher_staff_member_id
        assessment_id

    school_id и teacher_staff_member_id
    берутся только из текущего пользователя.

    Repository дополнительно проверяет:
        Assessment.input_mode == ONLINE
    """

    # =====================================================
    # SECURITY BOUNDARY
    # =====================================================

    school_id = require_school_id(
        user
    )

    teacher_staff_member_id = (
        require_staff_member_id(
            user
        )
    )

    # =====================================================
    # PAGE DATA
    # =====================================================

    page_data = (
        await TeacherOnlineAssessmentService
        .get_groups_page(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            assessment_id=assessment_id,
        )
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/online/groups.html",
        {
            "user": user,

            "dto": page_data,

            "assessment_id": (
                page_data.assessment_id
            ),

            "items": (
                page_data.items
            ),

            "total_groups": (
                page_data.total_groups
            ),

            "total_students": (
                page_data.total_students
            ),

            "assigned_count": (
                page_data.assigned_count
            ),

            "in_progress_count": (
                page_data.in_progress_count
            ),

            "pending_review_count": (
                page_data.pending_review_count
            ),

            "completed_count": (
                page_data.completed_count
            ),

            "groups_with_pending_review_count": (
                page_data
                .groups_with_pending_review_count
            ),

            "has_pending_review": (
                page_data.has_pending_review
            ),
        },
    )


@router.get(
    "/groups/{assessment_group_id}/students",
    name="teacher_online_assessment_students_page",
    response_class=HTMLResponse,
)
async def teacher_online_assessment_students_page(
    request: Request,
    assessment_group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_teacher_workspace),
):
    """
    Страница участников одной группы
    ONLINE Assessment текущего учителя.
    """

    school_id = require_school_id(
        user
    )

    teacher_staff_member_id = require_staff_member_id(
        user
    )

    page_data = (
        await TeacherOnlineAssessmentService
        .get_students_page(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            assessment_group_id=(
                assessment_group_id
            ),
        )
    )

    # Группа не существует либо недоступна
    # текущему учителю.
    if page_data.assessment_id <= 0:
        return render_error(
            templates,
            request,
            "teacher/assessment/online/students.html",
            {
                "user": user,
                "dto": page_data,
                "items": (),
                "assessment_id": 0,
                "assessment_group_id": assessment_group_id,
                "total_students": 0,
                "assigned_count": 0,
                "in_progress_count": 0,
                "pending_review_count": 0,
                "completed_count": 0,
                "absent_count": 0,
                "excused_count": 0,
                "not_completed_count": 0,
                "has_pending_review": False,
            },
            (
                "ONLINE Assessment тобы табылмады "
                "немесе оны көруге рұқсат жоқ."
            ),
            status_code=404,
        )

    return render(
        templates,
        request,
        "teacher/assessment/online/students.html",
        {
            "user": user,

            "dto": page_data,
            "items": page_data.items,

            "assessment_id": (
                page_data.assessment_id
            ),

            "assessment_group_id": (
                page_data.assessment_group_id
            ),

            "total_students": (
                page_data.total_students
            ),

            "assigned_count": (
                page_data.assigned_count
            ),

            "in_progress_count": (
                page_data.in_progress_count
            ),

            "pending_review_count": (
                page_data.pending_review_count
            ),

            "completed_count": (
                page_data.completed_count
            ),

            "absent_count": (
                page_data.absent_count
            ),

            "excused_count": (
                page_data.excused_count
            ),

            "not_completed_count": (
                page_data.not_completed_count
            ),

            "has_pending_review": (
                page_data.has_pending_review
            ),
        },
    )

# =========================================================
# STUDENT -> ANSWERS
# =========================================================


@router.get(
    "/students/{assessment_student_id}/review",
    name="teacher_online_assessment_student_review_page",
    response_class=HTMLResponse,
)
async def teacher_online_assessment_student_review_page(
        request: Request,
        assessment_student_id: int,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Страница проверки / просмотра ONLINE Assessment одного ученика.

    Показывает:
        - автоматически проверенные ответы;
        - ответы, ожидающие ручной проверки;
        - выставленные баллы;
        - итоговый результат.

    Security boundary:
        school_id
        teacher_staff_member_id
        assessment_student_id

    Навигация:
        from=results
            -> возврат в общие результаты AssessmentGroup

        иначе
            -> возврат в ONLINE students page
    """

    # =====================================================
    # SECURITY BOUNDARY
    # =====================================================

    school_id = require_school_id(
        user
    )

    teacher_staff_member_id = (
        require_staff_member_id(
            user
        )
    )

    # =====================================================
    # PAGE DATA
    # =====================================================

    try:
        page_data = (
            await TeacherAssessmentResultService
            .get_student_review_page(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                assessment_student_id=(
                    assessment_student_id
                ),
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=str(exc),
        ) from exc

    # =====================================================
    # NAVIGATION ORIGIN
    # =====================================================

    origin = (
        request.query_params.get("from")
        or ""
    ).strip()

    if origin == "results":
        back_url = request.url_for(
            "teacher_assessment_group_results_page",
            assessment_group_id=(
                page_data.assessment_group_id
            ),
        )
    else:
        origin = ""

        back_url = request.url_for(
            "teacher_online_assessment_students_page",
            assessment_group_id=(
                page_data.assessment_group_id
            ),
        )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/online/student_review.html",
        {
            "user": user,

            "dto": page_data,

            "assessment_id": (
                page_data.assessment_id
            ),

            "assessment_group_id": (
                page_data.assessment_group_id
            ),

            "assessment_student_id": (
                page_data.assessment_student_id
            ),

            "student_id": (
                page_data.student_id
            ),

            "student_name": (
                page_data.student_name
            ),

            "answers": (
                page_data.answers
            ),

            "total_answers": (
                page_data.total_answers
            ),

            "checked_count": (
                page_data.checked_count
            ),

            "pending_review_count": (
                page_data.pending_review_count
            ),

            "has_pending_review": (
                page_data.has_pending_review
            ),

            "back_url": str(
                back_url
            ),

            "origin": origin,

            "success": (
                request.query_params.get(
                    "success"
                )
            ),

            "error": (
                request.query_params.get(
                    "error"
                )
            ),
        },
    )

# =========================================================
# MANUAL GRADE ANSWER
# =========================================================


@router.post(
    "/answers/{answer_id}/grade",
    name="teacher_online_assessment_answer_grade",
)
async def teacher_online_assessment_answer_grade(
        request: Request,
        answer_id: int,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Выполнить ручную проверку одного ответа
    ONLINE Assessment.

    Security boundary:
        school_id
        teacher_staff_member_id
        answer_id

    Audit:
        checked_by_user_id = текущий User.id

    Из HTML-формы принимается:
        score
        assessment_student_id
        origin

    assessment_student_id используется
    только для redirect и НЕ даёт права доступа.

    origin используется только для сохранения
    контекста навигации после POST.
    Допустимое значение:
        results
    """

    # =====================================================
    # SECURITY BOUNDARY
    # =====================================================

    school_id = require_school_id(
        user
    )

    teacher_staff_member_id = (
        require_staff_member_id(
            user
        )
    )

    checked_by_user_id = user.id

    # =====================================================
    # FORM
    # =====================================================

    form = await request.form()

    origin = (
        str(
            form.get("origin")
            or ""
        )
        .strip()
    )

    if origin != "results":
        origin = ""

    assessment_student_raw = str(
        form.get(
            "assessment_student_id"
        )
        or ""
    ).strip()

    if not assessment_student_raw:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "Assessment student ID көрсетілмеген."
            ),
        )

    try:
        assessment_student_id = int(
            assessment_student_raw
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "Assessment student ID дұрыс емес."
            ),
        ) from exc

    if assessment_student_id <= 0:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "Assessment student ID дұрыс емес."
            ),
        )

    # =====================================================
    # REVIEW URL
    # =====================================================

    review_url = request.url_for(
        "teacher_online_assessment_student_review_page",
        assessment_student_id=(
            assessment_student_id
        ),
    )

    review_query_prefix = (
        "from=results&"
        if origin == "results"
        else ""
    )

    # =====================================================
    # SCORE
    # =====================================================

    try:
        score = _parse_score(
            form.get(
                "score"
            )
        )

    except ValueError as exc:
        # Здесь транзакционных изменений ещё нет.
        # Возвращаемся на ту же страницу с ошибкой.

        return RedirectResponse(
            url=(
                f"{review_url}"
                f"?{review_query_prefix}"
                f"error={str(exc)}"
            ),
            status_code=(
                status.HTTP_303_SEE_OTHER
            ),
        )

    # =====================================================
    # MANUAL GRADING
    # =====================================================

    try:
        await AssessmentManualGradingService.grade_answer(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            checked_by_user_id=(
                checked_by_user_id
            ),
            assessment_student_answer_id=(
                answer_id
            ),
            score=score,
        )

    except ValueError as exc:
        # grade_answer() владеет своей транзакцией
        # и rollback выполняет внутри Service Layer.

        return RedirectResponse(
            url=(
                f"{review_url}"
                f"?{review_query_prefix}"
                f"error={str(exc)}"
            ),
            status_code=(
                status.HTTP_303_SEE_OTHER
            ),
        )

    # =====================================================
    # REDIRECT
    # =====================================================

    return RedirectResponse(
        url=(
            f"{review_url}"
            f"?{review_query_prefix}"
            "success=graded"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )
