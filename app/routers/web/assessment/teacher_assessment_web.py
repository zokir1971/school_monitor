# app/routers/web/assessment/teacher_assessment_web.py

from __future__ import annotations
from app.modules.assessment.services.analytics_work_selection import prepare_work_selection, normalize_filters
from dataclasses import replace
import logging
from app.modules.assessment.enums import AssessmentCheckpoint

from datetime import date

from decimal import Decimal, InvalidOperation
from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request, HTTPException,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status
from starlette.responses import JSONResponse, RedirectResponse

from app.db.session import get_db
from app.db.types import enum_items
from app.modules.assessment.enums import AssessmentType, AssessmentMode, AssessmentParticipationStatus, AssessmentStatus
from app.modules.assessment.exporters.knowledge_quality_excel import KnowledgeQualityExcelExporter
from app.modules.assessment.repositories.assessment_repo import AssessmentRepo
from app.modules.assessment.repositories.knowledge_quality_analytics_repo import (
    KnowledgeQualityAnalyticsRepo,
)
from app.modules.assessment.schemas.assessment_create_schemas import AssessmentObjectiveInputDTO, AssessmentCreateDTO
from app.modules.assessment.schemas.manual_result_schemas import ManualStudentResultDTO, ManualObjectiveScoreDTO, \
    ManualAssessmentSaveDTO
from app.modules.assessment.services.assessment_completion_service import AssessmentCompletionService
from app.modules.assessment.services.assessment_list_service import AssessmentListService
from app.modules.assessment.services.knowledge_quality_analytics_service import (
    KnowledgeQualityAnalyticsService,
)
from app.modules.assessment.services.knowledge_quality_dynamics_service import KnowledgeQualityDynamicsService
from app.modules.assessment.services.knowledge_quality_export_service import KnowledgeQualityExportService
from app.modules.assessment.services.learning_objective_analysis_service import LearningObjectiveAnalysisService
from app.modules.assessment.services.manual_assessment_service import ManualAssessmentService
from app.modules.assessment.services.teacher_assessment_result_service import TeacherAssessmentResultService
from app.modules.education.repositories.class_subject_teacher_repo import SchoolClassSubjectTeacherRepo
from app.modules.education.repositories.school_class_repo import SchoolClassRepo
from app.modules.education.repositories.subject_repo import (
    SubjectRepo,
)
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
from app.routers.web.assessment.helpers.export_response import excel_download_response
from app.routers.web.helpers.render import render, render_error
from app.routers.web.helpers.request import parse_optional_int
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/teacher/assessment",
    tags=["teacher-assessment"],
)


def _academic_year_start(
        today: date | None = None,
) -> int:
    """
    Начало текущего учебного года.

    Август и позже относятся
    к новому учебному году.
    """

    current = today or date.today()

    if current.month >= 8:
        return current.year

    return current.year - 1


def _parse_decimal(
        value: object | None,
        *,
        field_name: str,
        required: bool = False,
) -> Decimal | None:
    """
    Преобразовать значение HTML-формы в Decimal.

    Поддерживает:
        20
        20.5
        20,5

    Пустое значение:
        required=False -> None
        required=True  -> ValueError
    """

    # =====================================================
    # NORMALIZE
    # =====================================================

    raw = (
        ""
        if value is None
        else str(value).strip()
    )

    if not raw:
        if required:
            raise ValueError(
                f"Поле «{field_name}» обязательно."
            )

        return None

    raw = raw.replace(
        ",",
        ".",
    )

    # =====================================================
    # PARSE
    # =====================================================

    try:
        result = Decimal(
            raw
        )

    except (
        InvalidOperation,
        ValueError,
    ) as exc:
        raise ValueError(
            f"Поле «{field_name}» "
            "содержит некорректное число."
        ) from exc

    # =====================================================
    # FINITE NUMBER
    # =====================================================

    if not result.is_finite():
        raise ValueError(
            f"Поле «{field_name}» "
            "должно содержать конечное число."
        )

    return result


def _parse_int_list(
        values: list[object],
) -> tuple[int, ...]:
    """
    Преобразовать набор HTML-значений
    в уникальный tuple[int, ...].

    Порядок сохраняется.
    """

    result: list[int] = []

    for value in values:
        raw = str(
            value or ""
        ).strip()

        if not raw:
            continue

        item_id = int(
            raw
        )

        if item_id <= 0:
            raise ValueError(
                "Получен некорректный идентификатор."
            )

        if item_id not in result:
            result.append(
                item_id
            )

    return tuple(
        result
    )

# =========================================================
# TEACHER ASSESSMENT LIST
# =========================================================


@router.get(
    "",
    name="teacher_assessment_list_page",
    response_class=HTMLResponse,
)
async def teacher_assessment_list_page(
        request: Request,

        academic_year_start: str | None = Query(
            default=None,
        ),

        subject_id: str | None = Query(
            default=None,
        ),

        grade_level: str | None = Query(
            default=None,
        ),

        status_value: str | None = Query(
            default=None,
            alias="status",
        ),

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Рабочий список Assessment текущего учителя.

    Показывает только AssessmentGroup,
    закреплённые за текущим teacher_staff_member_id.

    Security boundary:
        school_id берётся из текущего user;
        teacher_staff_member_id берётся из user.staff_member_id;
        teacher id не принимается из URL/query.
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
    # FILTERS
    # =====================================================

    selected_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    selected_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    selected_grade_level = (
        parse_optional_int(
            grade_level
        )
    )

    selected_status: AssessmentStatus | None = None

    if status_value:
        try:
            selected_status = AssessmentStatus(
                status_value
            )
        except ValueError:
            selected_status = None

    # =====================================================
    # PAGE DATA
    # =====================================================

    page_data = (
        await AssessmentListService
        .get_teacher_page(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            academic_year_start=(
                selected_academic_year
            ),
            subject_id=(
                selected_subject_id
            ),
            grade_level=(
                selected_grade_level
            ),
            status=(
                selected_status
            ),
        )
    )

    # =====================================================
    # URLS
    # =====================================================

    filter_action = request.url_for(
        "teacher_assessment_list_page"
    )

    clear_url = request.url_for(
        "teacher_assessment_list_page"
    )

    create_url = request.url_for(
        "teacher_assessment_create_page"
    )

    analytics_url = request.url_for(
        "teacher_assessment_analytics_page"
    )

    export_url = request.url_for(
        "teacher_assessment_analytics_export_excel"
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/list.html",
        {
            "user": user,

            "dto": page_data,

            "items": (
                page_data.items
            ),

            "total_count": (
                page_data.total_count
            ),

            "draft_count": (
                page_data.draft_count
            ),

            "completed_count": (
                page_data.completed_count
            ),

            # ---------------------------------------------
            # FILTER OPTIONS
            # ---------------------------------------------

            "academic_years": (
                page_data.academic_years
            ),

            "subjects": (
                page_data.subjects
            ),

            "grade_levels": (
                page_data.grade_levels
            ),

            "assessment_statuses": (
                enum_items(
                    AssessmentStatus
                )
            ),

            # ---------------------------------------------
            # SELECTED FILTERS
            # ---------------------------------------------

            "selected_academic_year": (
                page_data.selected_academic_year
            ),

            "selected_subject_id": (
                page_data.selected_subject_id
            ),

            "selected_grade_level": (
                page_data.selected_grade_level
            ),

            "selected_status": (
                page_data.selected_status
            ),

            # ---------------------------------------------
            # NAVIGATION
            # ---------------------------------------------

            "filter_action": str(
                filter_action
            ),

            "clear_url": str(
                clear_url
            ),

            "create_url": str(
                create_url
            ),

            "analytics_url": str(
                analytics_url
            ),

            "export_url": str(
                export_url
            ),

            "manual_route_name": (
                "teacher_assessment_manual_page"
            ),

            "complete_route_name": (
                "teacher_assessment_complete"
            ),

            "can_create": True,
            "can_export": True,
            # ---------------------------------------------
            # MESSAGES
            # ---------------------------------------------

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
# TEACHER ANALYTICS
# =========================================================


@router.get(
    "/analytics",
    name="teacher_assessment_analytics_page",
    response_class=HTMLResponse,
)
async def teacher_assessment_analytics_page(
        request: Request,

        academic_year_start: str | None = Query(
            default=None,
        ),

        subject_id: str | None = Query(
            default=None,
        ),

        grade_level: str | None = Query(
            default=None,
        ),

        work_key: str = Query(default='', max_length=40),
    checkpoint: str = Query(default='', max_length=20),
    work_page: int = Query(default=1, ge=1, le=100000),
    db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Аналитика качества знаний текущего учителя.

    Показывает:
        - общий итог учителя;
        - аналитику по классам;
        - реальные доступные фильтры.

    Security boundary:
        - school_id берётся из текущего user;
        - teacher_staff_member_id берётся из user.staff_member_id;
        - teacher id не принимается из URL/query.
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
    # AVAILABLE FILTERS
    # =====================================================

    filter_options = (
        await KnowledgeQualityAnalyticsRepo
        .get_teacher_filter_options(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
        )
    )

    # =====================================================
    # NORMALIZE FILTERS
    # =====================================================

    selected_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    selected_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    selected_grade_level = (
        parse_optional_int(
            grade_level
        )
    )

    # =====================================================
    # ACADEMIC YEAR
    # =====================================================

    if selected_academic_year is None:
        selected_academic_year = (
            filter_options.academic_years[0]
            if filter_options.academic_years
            else None
        )

    elif (
            selected_academic_year
            not in filter_options.academic_years
    ):
        selected_academic_year = (
            filter_options.academic_years[0]
            if filter_options.academic_years
            else None
        )

    # =====================================================
    # SUBJECT
    # =====================================================

    if (
            selected_subject_id is not None
            and selected_subject_id
            not in filter_options.subject_ids
    ):
        selected_subject_id = None

    # =====================================================
    # GRADE LEVEL
    # =====================================================

    if (
            selected_grade_level is not None
            and selected_grade_level
            not in filter_options.grade_levels
    ):
        selected_grade_level = None

    # =====================================================
    # TEACHER TOTAL
    # =====================================================

    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='teacher', scope_id=school_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='', teacher_staff_member_id=teacher_staff_member_id)
    work_key = work_selection['work_key']
    all_rows = await KnowledgeQualityAnalyticsService.get_all_work_rows(
            db, scope='teacher', scope_id=school_id,
            academic_year_start=selected_academic_year, subject_id=selected_subject_id,
            grade_level=selected_grade_level, checkpoint=work_selection['checkpoint'], teacher_staff_member_id=teacher_staff_member_id, offset=(work_page-1)*50, limit=51) if work_key == 'all' else ()


    teacher_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_teacher_analytics(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            academic_year_start=(
                selected_academic_year
            ),
            subject_id=(
                selected_subject_id
            ),
            grade_level=(
                selected_grade_level
            ),
            work_key=work_key,
        )
    )

    # =====================================================
    # TEACHER -> CLASSES
    # =====================================================

    class_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_teacher_class_analytics(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            academic_year_start=(
                selected_academic_year
            ),
            subject_id=(
                selected_subject_id
            ),
            grade_level=(
                selected_grade_level
            ),
            work_key=work_key,
        )
    )

    # =====================================================
    # KNOWLEDGE QUALITY DYNAMICS
    # =====================================================

    dynamics = None

    if selected_academic_year is not None:
        dynamics = (
            await KnowledgeQualityDynamicsService
            .get_school_dynamics(
                db,
                school_id=school_id,
                academic_year_start=(
                    selected_academic_year
                ),
                subject_id=(
                    selected_subject_id
                ),
                grade_level=(
                    selected_grade_level
                ),
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

    # =====================================================
    # SUBJECT OPTIONS
    # =====================================================

    subjects = (
        await SubjectRepo.get_active_by_ids(
            db,
            subject_ids=(
                filter_options.subject_ids
            ),
        )
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/analytics.html",
        {
            "user": user,
            "work_selection": work_selection,
            "all_work_rows": all_rows[:50], "all_work_next": len(all_rows)>50, "work_page": work_page,
            "all_work_scope": 'teacher',

            # ---------------------------------------------
            # SCOPE
            # ---------------------------------------------

            "school_id": school_id,

            "teacher_staff_member_id": (
                teacher_staff_member_id
            ),

            # ---------------------------------------------
            # ANALYTICS
            # ---------------------------------------------

            "dto": teacher_analytics,

            "dynamics": dynamics,

            "teacher_analytics": (
                teacher_analytics
            ),

            "class_analytics": (
                class_analytics
            ),

            "classes": (
                class_analytics.items
            ),

            "class_count": (
                class_analytics.item_count
            ),

            # ---------------------------------------------
            # FILTER OPTIONS
            # ---------------------------------------------

            "subjects": subjects,

            "academic_years": (
                filter_options.academic_years
            ),

            "grade_levels": (
                filter_options.grade_levels
            ),

            # ---------------------------------------------
            # SELECTED FILTERS
            # ---------------------------------------------

            "selected_academic_year": (
                selected_academic_year
            ),

            "selected_subject_id": (
                selected_subject_id
            ),

            "selected_grade_level": (
                selected_grade_level
            ),
        },
    )


# =========================================================
# TEACHER ANALYTICS -> EXCEL
# =========================================================


@router.get(
    "/analytics/export.xlsx",
    name="teacher_assessment_analytics_export_excel",
)
async def teacher_assessment_analytics_export_excel(
        academic_year_start: str | None = Query(
            default=None,
        ),

        subject_id: str | None = Query(
            default=None,
        ),

        grade_level: str | None = Query(
            default=None,
        ),

        work_key: str = Query(default='', max_length=40),
    checkpoint: str = Query(default='', max_length=20),
    db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Excel-экспорт аналитики качества знаний
    текущего учителя.

    Security boundary:
        school_id
        teacher_staff_member_id

    teacher id не принимается
    из URL или query params.
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
    # FILTERS
    # =====================================================

    selected_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    selected_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    selected_grade_level = (
        parse_optional_int(
            grade_level
        )
    )

    # =====================================================
    # EXPORT DTO
    # =====================================================

    filter_options = await KnowledgeQualityAnalyticsRepo.get_teacher_filter_options(db, school_id=school_id, teacher_staff_member_id=teacher_staff_member_id)
    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='teacher', scope_id=school_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='', teacher_staff_member_id=teacher_staff_member_id)
    work_key = work_selection['work_key']

    if work_selection['selected'] is None:
        raise HTTPException(status_code=400, detail=work_selection['prompt'])

    dto = (
        await KnowledgeQualityExportService
        .build_teacher_export(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            academic_year_start=(
                selected_academic_year
            ),
            subject_id=(
                selected_subject_id
            ),
            grade_level=(
                selected_grade_level
            ),
            work_key=work_key,
        )
    )

    # =====================================================
    # XLSX
    # =====================================================

    dto = replace(dto, work_title=work_selection['selected']['label'])
    if work_key == 'all':
        all_rows = await KnowledgeQualityAnalyticsService.get_all_work_rows(
            db, scope='teacher', scope_id=school_id,
            academic_year_start=selected_academic_year, subject_id=selected_subject_id,
            grade_level=selected_grade_level, checkpoint=work_selection['checkpoint'], teacher_staff_member_id=teacher_staff_member_id, limit=50001)
        if len(all_rows) > 50000:
            raise HTTPException(status_code=400, detail='Уточните фильтры: более 50000 строк. / Сүзгілерді нақтылаңыз: 50000 жолдан артық.')
        dto = replace(dto, rows=all_rows, summary=None, all_works=True,
                      work_summaries=KnowledgeQualityAnalyticsService.summarize_work_rows(all_rows))


    content = (
        KnowledgeQualityExcelExporter
        .build(
            dto
        )
    )

    # =====================================================
    # RESPONSE
    # =====================================================

    return excel_download_response(
        content=content,
        filename=(
            "bilim_sapasy_mugalim.xlsx"
        ),
    )


# =========================================================
# CREATE ASSESSMENT PAGE
# =========================================================


@router.get(
    "/create",
    name="teacher_assessment_create_page",
    response_class=HTMLResponse,
)
async def teacher_assessment_create_page(
        request: Request,

        academic_year_start: int | None = Query(
            default=None,
        ),

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Страница создания Assessment учителем.

    Учитель видит только:

        - свои предметы;
        - свои классы;
        - только активные назначения.

    Security boundary:
        school_id
        teacher_staff_member_id
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
    # ACADEMIC YEAR
    # =====================================================

    selected_year = (
        academic_year_start
        if academic_year_start is not None
        else _academic_year_start()
    )

    # =====================================================
    # TEACHER ASSIGNMENTS
    # =====================================================

    assignments = (
        await SchoolClassSubjectTeacherRepo
        .get_active_primary_for_teacher(
            db,
            school_id=school_id,
            staff_member_id=(
                teacher_staff_member_id
            ),
        )
    )

    # =====================================================
    # IDS
    # =====================================================

    subject_ids = tuple(
        dict.fromkeys(
            assignment.subject_id
            for assignment in assignments
        )
    )

    class_ids = tuple(
        dict.fromkeys(
            assignment.school_class_id
            for assignment in assignments
        )
    )

    # =====================================================
    # SUBJECTS
    # =====================================================

    subjects = (
        await SubjectRepo.get_active_by_ids(
            db,
            subject_ids=subject_ids,
        )
        if subject_ids
        else []
    )

    # =====================================================
    # CLASSES
    # =====================================================

    classes = (
        await SchoolClassRepo
        .get_many_by_ids_for_school(
            db,
            school_id=school_id,
            class_ids=class_ids,
        )
        if class_ids
        else []
    )

    # Учитель может иметь назначения
    # за несколько учебных лет.
    classes = [
        school_class
        for school_class in classes
        if (
                school_class.is_active
                and school_class.academic_year_start
                == selected_year
        )
    ]

    allowed_class_ids = {
        school_class.id
        for school_class in classes
    }

    allowed_subject_ids = {
        subject.id
        for subject in subjects
    }

    # =====================================================
    # CREATE MATRIX
    # =====================================================

    # Эта структура нужна шаблону:
    #
    # {
    #     subject_id: [class_id, ...]
    # }
    #
    # Благодаря ей JS не позволит выбрать
    # класс, где учитель не ведёт этот предмет.

    subject_class_map: dict[
        int,
        list[int],
    ] = {}

    for assignment in assignments:
        if (
                assignment.subject_id
                not in allowed_subject_ids
        ):
            continue

        if (
                assignment.school_class_id
                not in allowed_class_ids
        ):
            continue

        subject_class_map.setdefault(
            assignment.subject_id,
            [],
        ).append(
            assignment.school_class_id
        )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/create.html",
        {
            "user": user,

            "school_id": school_id,

            "academic_year_start": (
                selected_year
            ),

            "academic_year_label": (
                f"{selected_year}/"
                f"{selected_year + 1}"
            ),

            "subjects": subjects,
            "classes": classes,

            "subject_class_map": (
                subject_class_map
            ),

            "assessment_types": (
                enum_items(
                    AssessmentType
                )
            ),

            "assessment_modes": (
                enum_items(
                    AssessmentMode
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
# CREATE ASSESSMENT
# =========================================================


@router.post(
    "/create",
    name="teacher_assessment_create",
)
async def teacher_assessment_create(
        request: Request,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Создать Assessment текущим учителем.

    Security boundary:

        user
            ↓
        school_id
        teacher_staff_member_id
            ↓
        SchoolClassSubjectTeacher
            ↓
        subject + classes

    Значения subject_id / school_class_ids
    из HTML-формы сами по себе не дают права
    создавать Assessment.
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
    # FORM
    # =====================================================

    form = await request.form()

    # =====================================================
    # ACADEMIC YEAR
    # =====================================================

    academic_year_raw = str(
        form.get(
            "academic_year_start"
        )
        or ""
    ).strip()

    # selected_year должен существовать
    # до входа в основной try,
    # потому что он используется и в except.
    try:
        selected_year = (
            int(academic_year_raw)
            if academic_year_raw
            else _academic_year_start()
        )

    except ValueError:
        selected_year = (
            _academic_year_start()
        )

    try:
        # =================================================
        # BASIC
        # =================================================

        from app.modules.assessment.helpers.manual_work_parameters import normalize_manual_form
        form=normalize_manual_form(form)

        title = str(
            form.get("title") or ""
        ).strip()

        # The canonical bilingual name is generated by the service.

        description_raw = str(
            form.get("description") or ""
        ).strip()

        description = (
            description_raw
            if description_raw
            else None
        )

        # =================================================
        # ACADEMIC YEAR VALIDATION
        # =================================================

        if selected_year <= 0:
            raise ValueError(
                "Оқу жылы дұрыс көрсетілмеген."
            )

        # =================================================
        # SUBJECT
        # =================================================

        subject_raw = str(
            form.get("subject_id") or ""
        ).strip()

        if not subject_raw:
            raise ValueError(
                "Пәнді таңдаңыз."
            )

        subject_id = int(
            subject_raw
        )

        if subject_id <= 0:
            raise ValueError(
                "Пән дұрыс таңдалмаған."
            )

        # =================================================
        # ASSESSMENT TYPE
        # =================================================

        assessment_type_raw = str(
            form.get(
                "assessment_type"
            )
            or AssessmentType.DIAGNOSTIC.value
        ).strip()

        assessment_type = AssessmentType(
            assessment_type_raw
        )

        # =================================================
        # ASSESSMENT MODE
        # =================================================

        assessment_mode_raw = str(
            form.get(
                "assessment_mode"
            )
            or AssessmentMode.WITHOUT_OBJECTIVES.value
        ).strip()

        assessment_mode = AssessmentMode(
            assessment_mode_raw
        )

        # =================================================
        # DURATION
        # =================================================

        duration_raw = str(
            form.get(
                "duration_minutes"
            )
            or ""
        ).strip()

        duration_minutes: int | None = None

        if duration_raw:
            duration_minutes = int(
                duration_raw
            )

            if duration_minutes <= 0:
                raise ValueError(
                    "Assessment ұзақтығы "
                    "0 минуттан үлкен болуы керек."
                )

        # =================================================
        # MAX SCORE
        # =================================================

        max_score = _parse_decimal(
            form.get(
                "max_score"
            ),
            field_name=(
                "Максималды балл"
            ),
            required=True,
        )

        assert max_score is not None

        if max_score <= 0:
            raise ValueError(
                "Максималды балл "
                "0-ден үлкен болуы керек."
            )

        # =================================================
        # CLASSES
        # =================================================

        school_class_ids = (
            _parse_int_list(
                list(
                    form.getlist(
                        "school_class_ids"
                    )
                )
            )
        )

        if not school_class_ids:
            raise ValueError(
                "Кемінде бір сыныпты таңдаңыз."
            )

        # =================================================
        # TEACHER ASSIGNMENTS
        # =================================================

        assignments = (
            await SchoolClassSubjectTeacherRepo
            .get_active_primary_for_teacher(
                db,
                school_id=school_id,
                staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        # Серверная матрица доступа:
        #
        # subject_id
        #     -> set[class_id]

        allowed_classes_by_subject: dict[
            int,
            set[int],
        ] = {}

        for assignment in assignments:
            allowed_classes_by_subject.setdefault(
                assignment.subject_id,
                set(),
            ).add(
                assignment.school_class_id
            )

        allowed_class_ids = (
            allowed_classes_by_subject.get(
                subject_id,
                set(),
            )
        )

        if not allowed_class_ids:
            raise ValueError(
                "Сізге таңдалған пән бойынша "
                "Assessment құруға рұқсат жоқ."
            )

        forbidden_class_ids = (
            set(
                school_class_ids
            )
            - allowed_class_ids
        )

        if forbidden_class_ids:
            raise ValueError(
                "Таңдалған сыныптардың бір бөлігі "
                "осы пән бойынша сізге бекітілмеген."
            )

        # =================================================
        # CLASS / ACADEMIC YEAR VALIDATION
        # =================================================

        selected_classes = (
            await SchoolClassRepo
            .get_many_by_ids_for_school(
                db,
                school_id=school_id,
                class_ids=(
                    school_class_ids
                ),
            )
        )

        if (
            len(selected_classes)
            != len(school_class_ids)
        ):
            raise ValueError(
                "Таңдалған сыныптардың "
                "бір бөлігі табылмады."
            )

        invalid_year_classes = [
            school_class.name
            for school_class in selected_classes
            if (
                not school_class.is_active
                or
                school_class.academic_year_start
                != selected_year
            )
        ]

        if invalid_year_classes:
            raise ValueError(
                "Таңдалған оқу жылына сәйкес "
                "келмейтін сыныптар бар: "
                + ", ".join(
                    invalid_year_classes
                )
            )

        # =================================================
        # OBJECTIVES
        # =================================================

        objective_inputs: list[
            AssessmentObjectiveInputDTO
        ] = []

        if assessment_mode in {
            AssessmentMode.BY_OBJECTIVES,
            AssessmentMode.ASSESSMENT_BY_SECTION,
            AssessmentMode.ASSESSMENT_BY_QUARTER,
        }:
            objective_ids = (
                _parse_int_list(
                    list(
                        form.getlist(
                            "learning_objective_ids"
                        )
                    )
                )
            )

            if not objective_ids:
                raise ValueError(
                    "Бұл Assessment режимі үшін "
                    "кемінде бір оқу мақсатын таңдаңыз."
                )

            for (
                    order_no,
                    objective_id,
            ) in enumerate(
                objective_ids,
                start=1,
            ):
                objective_max_score = (
                    _parse_decimal(
                        form.get(
                            "objective_max_score_"
                            f"{objective_id}"
                        ),
                        field_name=(
                            "Оқу мақсатының "
                            "максималды баллы"
                        ),
                        required=True,
                    )
                )

                assert objective_max_score is not None

                if objective_max_score <= 0:
                    raise ValueError(
                        "Оқу мақсатының "
                        "максималды баллы "
                        "0-ден үлкен болуы керек."
                    )

                objective_inputs.append(
                    AssessmentObjectiveInputDTO(
                        learning_objective_id=(
                            objective_id
                        ),
                        max_score=(
                            objective_max_score
                        ),
                        order_no=order_no,
                    )
                )

        elif (
            assessment_mode
            == AssessmentMode.WITHOUT_OBJECTIVES
        ):
            pass

        else:
            raise ValueError(
                "Белгісіз Assessment режимі."
            )

        # =================================================
        # DTO
        # =================================================

        dto = AssessmentCreateDTO(
            school_id=school_id,

            subject_id=subject_id,

            created_by_user_id=(
                user.id
            ),

            title=title,
            quarter=int(form.get("naming_quarter")) if form.get("naming_quarter") else None,
            section_number=int(form.get("section_number")) if form.get("section_number") else None,
            checkpoint=AssessmentCheckpoint(form["checkpoint"]) if form.get("checkpoint") else None,

            school_class_ids=(
                school_class_ids
            ),

            assessment_type=(
                assessment_type
            ),

            assessment_mode=(
                assessment_mode
            ),

            max_score=(
                max_score
            ),

            description=(
                description
            ),

            duration_minutes=(
                duration_minutes
            ),

            # Teacher-created Assessment пока
            # не относится к campaign.
            campaign_id=None,

            objectives=tuple(
                objective_inputs
            ),
        )

        # =================================================
        # CREATE
        # =================================================

        assessment_id = (
            await ManualAssessmentService
            .create_assessment(
                db,
                dto=dto,
            )
        )

    except ValueError as exc:

        logging.getLogger(__name__).warning("manual_assessment_create_rejected role=teacher reason=%s",str(exc))
        await db.rollback()

        # После rollback ORM-user может
        # стать expired.
        await db.refresh(
            user
        )

        redirect_url = request.url_for(
            "teacher_assessment_create_page"
        )

        return RedirectResponse(
            url=(
                f"{redirect_url}"
                f"?academic_year_start={selected_year}"
                f"&error={str(exc)}"
            ),
            status_code=(
                status.HTTP_303_SEE_OTHER
            ),
        )

    # =====================================================
    # REDIRECT TO MANUAL ENTRY
    # =====================================================

    redirect_url = request.url_for(
        "teacher_assessment_manual_page",
        assessment_id=assessment_id,
    )

    return RedirectResponse(
        url=(
            f"{redirect_url}"
            f"?success=created"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )
# =========================================================
# MANUAL ENTRY PAGE
# =========================================================


@router.get(
    "/{assessment_id}/manual",
    name="teacher_assessment_manual_page",
    response_class=HTMLResponse,
)
async def teacher_assessment_manual_page(
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
    Страница ручного ввода результатов
    Assessment текущим учителем.

    Teacher видит только AssessmentGroup,
    закреплённые за его staff_member_id.

    Security boundary:
        school_id
        teacher_staff_member_id
        assessment_id
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
            await ManualAssessmentService
            .get_teacher_manual_entry_page(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
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
    # URLS
    # =====================================================

    form_action = request.url_for(
        "teacher_assessment_manual_page",
        assessment_id=assessment_id,
    )

    back_url = request.url_for(
        "teacher_assessment_list_page"
    )

    create_url = request.url_for(
        "teacher_assessment_create_page"
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "staff/assessment/manual_entry.html",
        {
            "user": user,

            "dto": page_data,
            "assessment": page_data,
            "groups": page_data.groups,

            "participation_statuses": (
                enum_items(
                    AssessmentParticipationStatus
                )
            ),

            "form_action": str(
                form_action
            ),

            "back_url": str(
                back_url
            ),

            "create_url": str(
                create_url
            ),

            "success": (
                request.query_params.get(
                    "success"
                )
            ),
        },
    )


# =========================================================
# SAVE MANUAL RESULTS
# =========================================================


@router.post(
    "/{assessment_id}/manual",
    name="teacher_assessment_manual_save",
)
async def teacher_assessment_manual_save(
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
    Сохранить ручные результаты
    Assessment текущим учителем.

    Teacher может отправить результаты
    только учеников своих AssessmentGroup.

    Общий score:

        WITHOUT_OBJECTIVES
            передаётся из формы;

        ASSESSMENT_BY_SECTION /
        ASSESSMENT_BY_QUARTER
            не передаётся;
            рассчитывается Service Layer
            как сумма objective_scores.
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
    # LOAD PAGE + ACCESS CHECK
    # =====================================================

    try:
        page_data = (
            await ManualAssessmentService
            .get_teacher_manual_entry_page(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
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
    # FORM
    # =====================================================

    form = await request.form()

    try:
        results: list[
            ManualStudentResultDTO
        ] = []

        # =================================================
        # STUDENTS
        # =================================================

        for group in page_data.groups:

            for student in group.students:

                student_id = (
                    student.assessment_student_id
                )

                # =========================================
                # PARTICIPATION STATUS
                # =========================================

                status_raw = str(
                    form.get(
                        f"status_{student_id}"
                    )
                    or (
                        student.participation_status
                        or AssessmentParticipationStatus
                        .ASSIGNED.value
                    )
                ).strip()

                participation_status = (
                    AssessmentParticipationStatus(
                        status_raw
                    )
                )

                # =========================================
                # NON-COMPLETED
                # =========================================

                if (
                    participation_status
                    != AssessmentParticipationStatus.COMPLETED
                ):
                    results.append(
                        ManualStudentResultDTO(
                            assessment_student_id=(
                                student_id
                            ),
                            participation_status=(
                                participation_status
                            ),
                            score=None,
                            objective_scores=(),
                        )
                    )

                    continue

                # =========================================
                # OBJECTIVE MODE
                # =========================================

                if page_data.has_objectives:

                    objective_scores: list[
                        ManualObjectiveScoreDTO
                    ] = []

                    for objective in (
                        page_data.objectives
                    ):
                        objective_score = (
                            _parse_decimal(
                                form.get(
                                    "objective_score_"
                                    f"{student_id}_"
                                    f"{objective.assessment_objective_id}"
                                ),
                                field_name=(
                                    f"{student.student_name}: "
                                    f"{objective.code}"
                                ),
                                required=True,
                            )
                        )

                        assert (
                            objective_score
                            is not None
                        )

                        objective_scores.append(
                            ManualObjectiveScoreDTO(
                                assessment_objective_id=(
                                    objective
                                    .assessment_objective_id
                                ),
                                score=(
                                    objective_score
                                ),
                            )
                        )

                    results.append(
                        ManualStudentResultDTO(
                            assessment_student_id=(
                                student_id
                            ),
                            participation_status=(
                                participation_status
                            ),

                            # В objective mode общий
                            # score клиент НЕ передаёт.
                            score=None,

                            objective_scores=tuple(
                                objective_scores
                            ),
                        )
                    )

                    continue

                # =========================================
                # WITHOUT OBJECTIVES
                # =========================================

                score = _parse_decimal(
                    form.get(
                        f"score_{student_id}"
                    ),
                    field_name=(
                        f"Балл: "
                        f"{student.student_name}"
                    ),
                    required=True,
                )

                assert score is not None

                results.append(
                    ManualStudentResultDTO(
                        assessment_student_id=(
                            student_id
                        ),
                        participation_status=(
                            participation_status
                        ),
                        score=score,
                        objective_scores=(),
                    )
                )

        # =================================================
        # DTO
        # =================================================

        dto = ManualAssessmentSaveDTO(
            assessment_id=(
                assessment_id
            ),
            results=tuple(
                results
            ),
        )

        # =================================================
        # SAVE
        # =================================================

        await ManualAssessmentService.save_teacher_results(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            dto=dto,
        )

    except ValueError as exc:
        # Service Layer сам rollback'ит
        # transactional save errors.
        #
        # Но rollback здесь также безопасен
        # для ошибок разбора формы.

        await db.rollback()

        # После rollback ORM user может
        # оказаться expired.
        await db.refresh(
            user
        )

        # =================================================
        # RELOAD PAGE DATA
        # =================================================

        page_data = (
            await ManualAssessmentService
            .get_teacher_manual_entry_page(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        # =================================================
        # URLS
        # =================================================

        form_action = request.url_for(
            "teacher_assessment_manual_page",
            assessment_id=assessment_id,
        )

        back_url = request.url_for(
            "teacher_assessment_list_page"
        )

        create_url = request.url_for(
            "teacher_assessment_create_page"
        )

        # =================================================
        # ERROR PAGE
        # =================================================

        return render_error(
            templates,
            request,
            "staff/assessment/manual_entry.html",
            ctx={
                "user": user,

                "dto": page_data,
                "assessment": page_data,
                "groups": page_data.groups,

                "participation_statuses": (
                    enum_items(
                        AssessmentParticipationStatus
                    )
                ),

                "form_action": str(
                    form_action
                ),

                "back_url": str(
                    back_url
                ),

                "create_url": str(
                    create_url
                ),
            },
            error=str(exc),
            status_code=400,
        )

    # =====================================================
    # REDIRECT
    # =====================================================

    redirect_url = request.url_for(
        "teacher_assessment_manual_page",
        assessment_id=assessment_id,
    )

    return RedirectResponse(
        url=(
            f"{redirect_url}"
            f"?success=saved"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )

# =========================================================
# COMPLETE ASSESSMENT
# =========================================================


@router.post(
    "/{assessment_id}/complete",
    name="teacher_assessment_complete",
)
async def teacher_assessment_complete(
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
    Завершить Assessment текущим учителем.

    Учитель может завершить Assessment только если
    ВСЕ его AssessmentGroup принадлежат этому учителю.

    После завершения:
        - создаётся AssessmentQualitySummary;
        - Assessment переводится в COMPLETED;
        - результаты становятся финальными.
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
    # COMPLETE
    # =====================================================

    try:
        await AssessmentCompletionService.complete_for_teacher(
            db,
            school_id=school_id,
            teacher_staff_member_id=(
                teacher_staff_member_id
            ),
            assessment_id=assessment_id,
        )

    except ValueError as exc:
        redirect_url = request.url_for(
            "teacher_assessment_list_page"
        )

        return RedirectResponse(
            url=(
                f"{redirect_url}"
                f"?error={str(exc)}"
            ),
            status_code=(
                status.HTTP_303_SEE_OTHER
            ),
        )

    # =====================================================
    # REDIRECT
    # =====================================================

    redirect_url = request.url_for(
        "teacher_assessment_list_page"
    )

    return RedirectResponse(
        url=(
            f"{redirect_url}"
            "?success=completed"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


# =========================================================
# LEARNING OBJECTIVES API
# =========================================================


@router.get(
    "/api/learning-objectives",
    name="teacher_assessment_learning_objectives",
    response_class=JSONResponse,
)
async def teacher_assessment_learning_objectives(
        subject_id: int = Query(
            ...,
            gt=0,
        ),
        grade_level: int = Query(
            ...,
            ge=1,
            le=12,
        ),
        quarter: int | None = Query(None,ge=1,le=4),
        db: AsyncSession = Depends(
            get_db
        ),
        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Учебные цели предмета и параллели
    для формы создания Assessment учителем.

    Доступ разрешён только текущему teacher.
    """

    # Проверяем полноценный teacher scope,
    # даже если school_id непосредственно
    # в этом read-query не используется.
    require_school_id(
        user
    )

    require_staff_member_id(
        user
    )

    objectives = (
        await AssessmentRepo
        .get_learning_objectives(
            db,
            subject_id=subject_id,
            grade_level=grade_level,
            quarter=quarter,
        )
    )

    return JSONResponse(
        content={
            "items": [
                {
                    "id": objective.id,
                    "code": objective.code,
                    "title": objective.title_kz,
                    "grade_level": (
                        objective.grade_level
                    ),
                }
                for objective in objectives
            ]
        }
    )


# =========================================================
# CLASS -> ASSESSMENTS
# =========================================================

@router.get(
    "/classes/{school_class_id}/assessments",
    name="teacher_assessment_class_assessments_page",
    response_class=HTMLResponse,
)
async def teacher_assessment_class_assessments_page(
        request: Request,
        school_class_id: int,

        academic_year_start: str | None = Query(
            default=None,
        ),

        subject_id: str | None = Query(
            default=None,
        ),

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Список Assessment текущего учителя
    по конкретному классу.

    Дополнительно передаёт динамику качества знаний
    выбранного класса по официальным контрольным точкам.

    Security boundary:
        school_id
        teacher_staff_member_id

    school_class_id из URL сам по себе
    не даёт доступа к чужому классу.
    """

    school_id = require_school_id(
        user
    )

    teacher_staff_member_id = (
        require_staff_member_id(
            user
        )
    )

    selected_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    selected_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    try:
        page_data = (
            await TeacherAssessmentResultService
            .get_class_assessments(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                school_class_id=(
                    school_class_id
                ),
                academic_year_start=(
                    selected_academic_year
                ),
                subject_id=(
                    selected_subject_id
                ),
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    dynamics = None

    if page_data.academic_year_start is not None:
        dynamics = (
            await KnowledgeQualityDynamicsService
            .get_school_dynamics(
                db,
                school_id=school_id,
                academic_year_start=(
                    page_data.academic_year_start
                ),
                subject_id=(
                    page_data.subject_id
                ),
                school_class_id=(
                    page_data.school_class_id
                ),
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

    return render(
        templates,
        request,
        "teacher/assessment/class_assessments.html",
        {
            "user": user,

            "dto": page_data,

            "school_class_id": (
                page_data.school_class_id
            ),
            "class_name": (
                page_data.class_name
            ),

            "items": (
                page_data.items
            ),
            "item_count": (
                page_data.item_count
            ),

            "selected_academic_year": (
                page_data.academic_year_start
            ),
            "selected_subject_id": (
                page_data.subject_id
            ),

            "dynamics": dynamics,
        },
    )

# =========================================================
# ASSESSMENT GROUP -> STUDENTS / OBJECTIVES
# =========================================================


@router.get(
    "/groups/{assessment_group_id}/results",
    name="teacher_assessment_group_results_page",
    response_class=HTMLResponse,
)
async def teacher_assessment_group_results_page(
        request: Request,
        assessment_group_id: int,

        academic_year_start: str | None = Query(
            default=None,
        ),

        subject_id: str | None = Query(
            default=None,
        ),

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Результаты учеников конкретной AssessmentGroup
    текущего учителя.

    Для Assessment с учебными целями
    дополнительно передаётся Objective Analytics.

    Security boundary:
        school_id
        teacher_staff_member_id
        assessment_group_id

    teacher id не принимается из URL/query.
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
    # RETURN FILTERS
    # =====================================================

    selected_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    selected_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    # =====================================================
    # STUDENT RESULTS
    # =====================================================

    try:
        page_data = (
            await TeacherAssessmentResultService
            .get_assessment_students(
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

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # =====================================================
    # OBJECTIVE ANALYTICS
    # =====================================================

    try:
        objective_analytics = (
            await LearningObjectiveAnalysisService
            .get_teacher_assessment_objectives_page(
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

    except ValueError:
        # Нормальный сценарий для
        # WITHOUT_OBJECTIVES.
        objective_analytics = None
    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/student_results.html",
        {
            "user": user,

            # ---------------------------------------------
            # MAIN DTO
            # ---------------------------------------------

            "dto": page_data,

            # ---------------------------------------------
            # OBJECTIVE ANALYTICS
            # ---------------------------------------------

            "objective_analytics": (
                objective_analytics
            ),

            "has_objectives": (
                    objective_analytics is not None and bool(objective_analytics.objectives)
            ),

            # ---------------------------------------------
            # RETURN FILTERS
            # ---------------------------------------------

            "selected_academic_year": (
                selected_academic_year
            ),

            "selected_subject_id": (
                selected_subject_id
            ),

            # ---------------------------------------------
            # ASSESSMENT
            # ---------------------------------------------

            "assessment_id": (
                page_data.assessment_id
            ),

            "assessment_group_id": (
                page_data.assessment_group_id
            ),

            "title": (
                page_data.title
            ),

            "subject_name": (
                page_data.subject_name
            ),

            # ---------------------------------------------
            # CLASS
            # ---------------------------------------------

            "class_name": (
                page_data.class_name
            ),

            "grade_level": (
                page_data.grade_level
            ),

            # ---------------------------------------------
            # SCORE
            # ---------------------------------------------

            "max_score": (
                page_data.max_score
            ),

            "max_score_display": (
                page_data.max_score_display
            ),

            # ---------------------------------------------
            # STUDENTS
            # ---------------------------------------------

            "students": (
                page_data.students
            ),

            "student_count": (
                page_data.student_count
            ),
        },
    )


# =========================================================
# ASSESSMENT GROUP RESULTS -> EXCEL
# =========================================================


@router.get(
    (
        "/groups/{assessment_group_id}"
        "/results/export.xlsx"
    ),
    name=(
        "teacher_assessment_group_results_export_excel"
    ),
)
async def teacher_assessment_group_results_export_excel(
    assessment_group_id: int,
    academic_year_start: str | None = Query(default=None),
    subject_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_teacher_workspace),
):
    """
    Excel-экспорт результатов конкретной
    AssessmentGroup текущего учителя.

    Workbook:

        1. Оқушылар нәтижелері

        2. Оқу мақсаттары
           только если Assessment содержит
           учебные цели.

    Источники данных полностью совпадают
    со страницей student_results.html.

    Security boundary:

        school_id
        teacher_staff_member_id

    assessment_group_id из URL сам по себе
    не даёт доступа к чужому Assessment.
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
    # RETURN FILTERS
    # =====================================================

    selected_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    selected_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    # Эти значения сейчас нужны только
    # для сохранения симметрии с HTML route.
    #
    # Сам Excel строится по конкретной
    # AssessmentGroup.
    _ = (
        selected_academic_year,
        selected_subject_id,
    )

    # =====================================================
    # STUDENT RESULTS
    # =====================================================

    try:
        page_data = (
            await TeacherAssessmentResultService
            .get_assessment_students(
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

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_404_NOT_FOUND
            ),
            detail=str(exc),
        ) from exc

    # =====================================================
    # OBJECTIVE ANALYTICS
    # =====================================================

    try:
        objective_analytics = (
            await LearningObjectiveAnalysisService
            .get_teacher_assessment_objectives_page(
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

    except ValueError:
        # Нормальный сценарий:
        #
        # WITHOUT_OBJECTIVES
        #
        # Тогда workbook будет содержать
        # только лист результатов учеников.
        objective_analytics = None

    # =====================================================
    # XLSX
    # =====================================================

    content = (
        KnowledgeQualityExcelExporter
        .build_teacher_group_results(
            page_data=page_data,
            objective_analytics=(
                objective_analytics
            ),
        )
    )

    # =====================================================
    # FILENAME
    # =====================================================

    filename = (
        f"assessment_{page_data.assessment_id}_"
        f"class_{page_data.school_class_id}_"
        f"results.xlsx"
    )

    # =====================================================
    # RESPONSE
    # =====================================================

    return excel_download_response(
        content=content,
        filename=filename,
    )


# =========================================================
# OBJECTIVE -> STUDENTS
# =========================================================

@router.get(
    (
            "/groups/{assessment_group_id}"
            "/objectives/{assessment_objective_id}"
    ),
    name="teacher_assessment_objective_students_page",
    response_class=HTMLResponse,
)
async def teacher_assessment_objective_students_page(
        request: Request,
        assessment_group_id: int,
        assessment_objective_id: int,

        academic_year_start: str | None = Query(
            default=None,
        ),

        subject_id: str | None = Query(
            default=None,
        ),

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_teacher_workspace
        ),
):
    """
    Drill-down одной учебной цели:

        AssessmentObjective
            ↓
        ученики AssessmentGroup
            ↓
        индивидуальные objective results

    Возвращаются также:
        ABSENT
        EXCUSED
        NOT_COMPLETED

    без искусственных результатов.
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
    # RETURN FILTERS
    # =====================================================

    selected_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    selected_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    # =====================================================
    # PAGE DATA
    # =====================================================

    try:
        page_data = (
            await LearningObjectiveAnalysisService
            .get_teacher_objective_students_page(
                db,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
                assessment_group_id=(
                    assessment_group_id
                ),
                assessment_objective_id=(
                    assessment_objective_id
                ),
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "teacher/assessment/objective_students.html",
        {
            "user": user,

            "dto": page_data,

            "assessment_id": (
                page_data.assessment_id
            ),

            "assessment_group_id": (
                page_data.assessment_group_id
            ),

            "assessment_title": (
                page_data.assessment_title
            ),

            "subject_name": (
                page_data.subject_name
            ),

            "school_class_id": (
                page_data.school_class_id
            ),

            "class_name": (
                page_data.class_name
            ),

            "grade_level": (
                page_data.grade_level
            ),

            "assessment_objective_id": (
                page_data.assessment_objective_id
            ),

            "learning_objective_id": (
                page_data.learning_objective_id
            ),

            "objective_code": (
                page_data.objective_code
            ),

            "objective_title": (
                page_data.objective_title
            ),

            "objective_max_score": (
                page_data.objective_max_score
            ),

            "objective_max_score_display": (
                page_data.objective_max_score_display
            ),

            "students": (
                page_data.students
            ),

            "student_count": (
                page_data.student_count
            ),

            "selected_academic_year": (
                selected_academic_year
            ),

            "selected_subject_id": (
                selected_subject_id
            ),
        },
    )
