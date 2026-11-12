# app/routers/web/assessment/staff_assessment_web.py

from __future__ import annotations
from app.modules.assessment.services.analytics_work_selection import prepare_work_selection, normalize_filters
from dataclasses import replace
import logging

from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.db.session import get_db
from app.db.types import enum_items
from app.modules.assessment.enums import (
    AssessmentParticipationStatus,
    AssessmentType, AssessmentStatus, AssessmentMode, AssessmentCheckpoint,
)
from app.modules.assessment.exporters.knowledge_quality_excel import KnowledgeQualityExcelExporter
from app.modules.assessment.repositories.assessment_repo import (
    AssessmentRepo,
)
from app.modules.assessment.schemas.assessment_create_schemas import (
    AssessmentCreateDTO,
    AssessmentObjectiveInputDTO,
)
from app.modules.assessment.schemas.manual_result_schemas import ManualStudentResultDTO, ManualObjectiveScoreDTO, \
    ManualAssessmentSaveDTO
from app.modules.assessment.services.assessment_completion_service import AssessmentCompletionService
from app.modules.assessment.services.assessment_list_service import AssessmentListService
from app.modules.assessment.services.knowledge_quality_analytics_service import KnowledgeQualityAnalyticsService
from app.modules.assessment.services.knowledge_quality_export_service import KnowledgeQualityExportService
from app.modules.assessment.services.manual_assessment_service import (
    ManualAssessmentService,
)
from app.modules.education.repositories.school_class_repo import (
    SchoolClassRepo,
)
from app.modules.education.repositories.subject_repo import (
    SubjectRepo,
)
from app.modules.staff.utils.staff_require_school import (
    require_school_id,
)
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.assessment.helpers.export_response import excel_download_response
from app.routers.web.helpers.render import (
    render,
    render_error,
)
from app.routers.web.helpers.request import parse_optional_int
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/staff/assessment",
    tags=["staff-assessment"],
)


# =========================================================
# HELPERS
# =========================================================


def _academic_year_start(
        today: date | None = None,
) -> int:
    """
    Возвращает начало текущего учебного года.

    Например:
        август 2026 -> 2026
        январь 2027 -> 2026

    В School Monitor август относится уже
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
    Преобразование значения HTML-формы в Decimal.

    Поддерживает:
        30
        30.5
        30,5
    """

    raw = str(value or "").strip()

    if not raw:
        if required:
            raise ValueError(
                f"Поле «{field_name}» обязательно."
            )

        return None

    raw = raw.replace(",", ".")

    try:
        result = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(
            f"Поле «{field_name}» содержит "
            f"некорректное число."
        ) from exc

    if not result.is_finite():
        raise ValueError(
            f"Поле «{field_name}» должно содержать "
            f"конечное число."
        )

    return result


def _parse_int_list(
        values: list[object],
) -> tuple[int, ...]:
    """
    Безопасно преобразует список значений формы в int.
    """

    result: list[int] = []

    for value in values:
        raw = str(value or "").strip()

        if not raw:
            continue

        try:
            parsed = int(raw)
        except ValueError as exc:
            raise ValueError(
                "Получен некорректный идентификатор."
            ) from exc

        if parsed <= 0:
            raise ValueError(
                "Идентификатор должен быть больше 0."
            )

        result.append(parsed)

    return tuple(result)


# =========================================================
# ASSESSMENT LIST
# =========================================================


@router.get(
    "",
    name="staff_assessment_list_page",
    response_class=HTMLResponse,
)
async def staff_assessment_list_page(
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
            require_roles(
                UserRole.SCHOOL_ADMIN,
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Операционный список Assessment текущей школы.

    Фильтры:
        - учебный год;
        - предмет;
        - параллель;
        - статус.

    Источник filter options:
        существующие Assessment / AssessmentGroup snapshots.

    Текущие active Subject / SchoolClass
    для исторического списка не используются.
    """

    # =====================================================
    # SECURITY BOUNDARY
    # =====================================================

    school_id = require_school_id(
        user
    )

    # =====================================================
    # NORMALIZE QUERY PARAMS
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
    # BASIC VALIDATION
    # =====================================================

    if (
            selected_academic_year is not None
            and selected_academic_year <= 0
    ):
        selected_academic_year = None

    if (
            selected_subject_id is not None
            and selected_subject_id <= 0
    ):
        selected_subject_id = None

    if (
            selected_grade_level is not None
            and not 1 <= selected_grade_level <= 12
    ):
        selected_grade_level = None

    # =====================================================
    # STATUS
    # =====================================================

    selected_status: AssessmentStatus | None = None

    if status_value:
        normalized_status = (
            status_value.strip()
        )

        if normalized_status:
            try:
                selected_status = AssessmentStatus(
                    normalized_status
                )
            except ValueError:
                selected_status = None

    # =====================================================
    # PAGE DATA
    # =====================================================

    page_data = (
        await AssessmentListService
        .get_school_page(
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
            status=(
                selected_status
            ),
        )
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "staff/assessment/list.html",
        {
            "user": user,

            "dto": page_data,
            "items": page_data.items,

            "total_count": (
                page_data.total_count
            ),
            "draft_count": (
                page_data.draft_count
            ),
            "completed_count": (
                page_data.completed_count
            ),

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
            # SHARED TEMPLATE URLS
            # ---------------------------------------------

            "filter_action": str(
                request.url_for(
                    "staff_assessment_list_page"
                )
            ),

            "clear_url": str(
                request.url_for(
                    "staff_assessment_list_page"
                )
            ),

            "create_url": str(
                request.url_for(
                    "staff_assessment_create_page"
                )
            ),

            "analytics_url": str(
                request.url_for(
                    "staff_assessment_analytics_page"
                )
            ),

            "export_url": str(
                request.url_for(
                    "staff_assessment_analytics_export_excel"
                )
            ),

            "manual_route_name": (
                "staff_assessment_manual_page"
            ),

            "complete_route_name": (
                "staff_assessment_complete"
            ),

            "can_create": (user.role == UserRole.SCHOOL_STAFF),
            "can_export": True,

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
# CREATE PAGE
# =========================================================


@router.get(
    "/create",
    name="staff_assessment_create_page",
    response_class=HTMLResponse,
)
async def staff_assessment_create_page(
        request: Request,
        academic_year_start: int | None = Query(
            default=None,
        ),
        db: AsyncSession = Depends(
            get_db
        ),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Страница создания Assessment сотрудником школы.

    Сотрудник школы может выбирать:

        - любой активный предмет;
        - любые активные классы школы
          выбранного учебного года;
        - любой поддерживаемый AssessmentMode.

    Учитель конкретного класса определяется
    Service Layer автоматически через:

        school
        + subject
        + class
        -> primary teacher.
    """

    # =====================================================
    # SCHOOL
    # =====================================================

    school_id = require_school_id(
        user
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
    # SUBJECTS
    # =====================================================

    subjects = (
        await SubjectRepo.get_active_all(
            db,
        )
    )

    # =====================================================
    # CLASSES
    # =====================================================

    classes = (
        await SchoolClassRepo
        .get_active_by_school_and_year(
            db,
            school_id=school_id,
            academic_year_start=(
                selected_year
            ),
        )
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "staff/assessment/create.html",
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

            "assessment_checkpoints": (
                enum_items(
                    AssessmentCheckpoint
                )
            ),

            "form_data": {},

            "selected_class_ids": set(),
            "selected_objective_ids": set(),

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
    name="staff_assessment_create",
)
async def staff_assessment_create(
        request: Request,
        db: AsyncSession = Depends(
            get_db
        ),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Создание Assessment сотрудником школы.

    Сотрудник может создать Assessment:

        WITHOUT_OBJECTIVES
            диагностическая работа;

        ASSESSMENT_BY_SECTION
            БЖБ / СОР;

        ASSESSMENT_BY_QUARTER
            ТЖБ / СОЧ.

    Фактический учитель определяется
    ManualAssessmentService отдельно
    для каждого выбранного класса.
    """

    # =====================================================
    # SCHOOL
    # =====================================================

    school_id = require_school_id(
        user
    )

    # =====================================================
    # FORM
    # =====================================================

    form = await request.form()

    school_class_ids: tuple[
        int,
        ...
    ] = ()

    objective_ids: tuple[
        int,
        ...
    ] = ()

    try:
        # =================================================
        # TITLE
        # =================================================

        from app.modules.assessment.helpers.manual_work_parameters import normalize_manual_form
        form=normalize_manual_form(form)

        title = str(
            form.get("title")
            or ""
        ).strip()

        # =================================================
        # DESCRIPTION
        # =================================================

        description_raw = str(
            form.get("description")
            or ""
        ).strip()

        description = (
            description_raw
            if description_raw
            else None
        )

        # =================================================
        # SUBJECT
        # =================================================

        subject_raw = str(
            form.get("subject_id")
            or ""
        ).strip()

        if not subject_raw:
            raise ValueError(
                "Необходимо выбрать предмет."
            )

        subject_id = int(
            subject_raw
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

        assessment_type = (
            AssessmentType(
                assessment_type_raw
            )
        )

        # =================================================
        # ASSESSMENT MODE
        # =================================================

        assessment_mode_raw = str(
            form.get(
                "assessment_mode"
            )
            or AssessmentMode
            .WITHOUT_OBJECTIVES
            .value
        ).strip()

        assessment_mode = (
            AssessmentMode(
                assessment_mode_raw
            )
        )

        # =================================================
        # ASSESSMENT CHECKPOINT
        # =================================================

        checkpoint_raw = str(
            form.get(
                "checkpoint"
            )
            or ""
        ).strip()

        checkpoint = (
            AssessmentCheckpoint(
                checkpoint_raw
            )
            if checkpoint_raw
            else None
        )

        # =================================================
        # MAX SCORE
        # =================================================

        max_score = _parse_decimal(
            form.get(
                "max_score"
            ),
            field_name=(
                "Максимальный балл"
            ),
            required=True,
        )

        assert (
                max_score is not None
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

        duration_minutes = (
            int(
                duration_raw
            )
            if duration_raw
            else None
        )

        if (
                duration_minutes is not None
                and duration_minutes <= 0
        ):
            raise ValueError(
                "Продолжительность Assessment "
                "должна быть больше 0 минут."
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
                "Необходимо выбрать "
                "хотя бы один класс."
            )

        # =================================================
        # OBJECTIVES
        # =================================================

        objective_ids = (
            _parse_int_list(
                list(
                    form.getlist(
                        "learning_objective_ids"
                    )
                )
            )
        )

        objective_inputs: list[
            AssessmentObjectiveInputDTO
        ] = []

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
                        "Максимальный балл "
                        "учебной цели"
                    ),
                    required=True,
                )
            )

            assert (
                    objective_max_score
                    is not None
            )

            objective_inputs.append(
                AssessmentObjectiveInputDTO(
                    learning_objective_id=(
                        objective_id
                    ),
                    max_score=(
                        objective_max_score
                    ),
                    order_no=(
                        order_no
                    ),
                )
            )

        # =================================================
        # DTO
        # =================================================

        dto = AssessmentCreateDTO(
            school_id=school_id,

            subject_id=(
                subject_id
            ),

            created_by_user_id=(
                user.id
            ),

            title=title,
            quarter=int(form.get("naming_quarter")) if form.get("naming_quarter") else None,
            section_number=int(form.get("section_number")) if form.get("section_number") else None,
            description=description,

            assessment_type=(
                assessment_type
            ),

            assessment_mode=(
                assessment_mode
            ),

            checkpoint=(
                checkpoint
            ),

            school_class_ids=(
                school_class_ids
            ),

            max_score=(
                max_score
            ),

            duration_minutes=(
                duration_minutes
            ),

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

    except (
            ValueError,
            InvalidOperation,
    ) as exc:

        logging.getLogger(__name__).warning("manual_assessment_create_rejected role=staff reason=%s",str(exc))

        await db.rollback()

        # rollback делает ORM user expired.
        await db.refresh(
            user
        )

        # =================================================
        # RESTORE ACADEMIC YEAR
        # =================================================

        selected_year_raw = str(
            form.get(
                "academic_year_start"
            )
            or ""
        ).strip()

        try:
            selected_year = (
                int(
                    selected_year_raw
                )
                if selected_year_raw
                else _academic_year_start()
            )
        except ValueError:
            selected_year = (
                _academic_year_start()
            )

        # =================================================
        # RELOAD OPTIONS
        # =================================================

        subjects = (
            await SubjectRepo.get_active_all(
                db,
            )
        )

        classes = (
            await SchoolClassRepo
            .get_active_by_school_and_year(
                db,
                school_id=school_id,
                academic_year_start=(
                    selected_year
                ),
            )
        )

        # =================================================
        # RENDER ERROR
        # =================================================

        return render_error(
            templates,
            request,
            "staff/assessment/create.html",
            ctx={
                "user": user,

                "school_id": (
                    school_id
                ),

                "academic_year_start": (
                    selected_year
                ),

                "academic_year_label": (
                    f"{selected_year}/"
                    f"{selected_year + 1}"
                ),

                "subjects": (
                    subjects
                ),

                "classes": (
                    classes
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

                "assessment_checkpoints": (
                    enum_items(
                        AssessmentCheckpoint
                    )
                ),

                "form_data": {
                    key: form.get(
                        key
                    )
                    for key in form.keys()
                },

                "selected_class_ids": (
                    set(
                        school_class_ids
                    )
                ),

                "selected_objective_ids": (
                    set(
                        objective_ids
                    )
                ),
            },
            error=str(
                exc
            ),
            status_code=400,
        )

    # =====================================================
    # REDIRECT
    # =====================================================

    return RedirectResponse(
        url=request.url_for(
            "staff_assessment_manual_page",
            assessment_id=(
                assessment_id
            ),
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
    name="staff_assessment_learning_objectives",
)
async def staff_assessment_learning_objectives(
        subject_id: int = Query(..., gt=0),
        grade_level: int = Query(
            ...,
            ge=1,
            le=12,
        ),
        quarter: int | None = Query(None,ge=1,le=4),
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Учебные цели выбранного предмета и параллели.

    Используется create.html после выбора
    предмета и класса.
    """

    # Одновременно проверяем, что пользователь
    # действительно относится к школе.
    require_school_id(user)

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
        {
            "items": [
                {
                    "id": objective.id,
                    "code": objective.code,
                    "title_kz": (
                        objective.title_kz
                    ),
                    "grade_level": (
                        objective.grade_level
                    ),
                }
                for objective in objectives
            ]
        }
    )


# =========================================================
# MANUAL ENTRY PAGE
# =========================================================


@router.get(
    "/{assessment_id}/manual",
    name="staff_assessment_manual_page",
    response_class=HTMLResponse,
)
async def staff_assessment_manual_page(
        request: Request,
        assessment_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_ADMIN,
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Страница ручного ввода результатов.
    """

    # =====================================================
    # SCHOOL
    # =====================================================

    school_id = require_school_id(
        user
    )

    # =====================================================
    # PAGE DATA
    # =====================================================

    try:
        page_data = (
            await ManualAssessmentService
            .get_manual_entry_page(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # =====================================================
    # SHARED TEMPLATE URLS
    # =====================================================

    back_url = request.url_for(
        "staff_assessment_list_page"
    )

    form_action = request.url_for(
        "staff_assessment_manual_page",
        assessment_id=assessment_id,
    )

    create_url = request.url_for(
        "staff_assessment_create_page"
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

            "participation_statuses": enum_items(
                AssessmentParticipationStatus
            ),

            "back_url": str(
                back_url
            ),

            "form_action": str(
                form_action
            ),

            "create_url": str(
                create_url
            ),

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


@router.post(
    "/{assessment_id}/manual",
    name="staff_assessment_manual_save",
)
async def staff_assessment_manual_save(
        request: Request,
        assessment_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_ADMIN,
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Пакетное сохранение ручных результатов.

    WITHOUT_OBJECTIVES:
        клиент передаёт общий score ученика.

    ASSESSMENT_BY_SECTION /
    ASSESSMENT_BY_QUARTER:
        клиент передаёт баллы по каждой
        учебной цели;

        общий score клиент не передаёт;

        итоговый score, percent и grade
        рассчитывает Service Layer.
    """

    # =====================================================
    # SCHOOL
    # =====================================================

    school_id = require_school_id(
        user
    )

    # =====================================================
    # PAGE DATA
    # =====================================================

    try:
        page_data = (
            await ManualAssessmentService
            .get_manual_entry_page(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # =====================================================
    # SHARED TEMPLATE URLS
    # =====================================================

    back_url = request.url_for(
        "staff_assessment_list_page"
    )

    form_action = request.url_for(
        "staff_assessment_manual_page",
        assessment_id=assessment_id,
    )

    create_url = request.url_for(
        "staff_assessment_create_page"
    )

    # =====================================================
    # FORM
    # =====================================================

    form = await request.form()

    results: list[
        ManualStudentResultDTO
    ] = []

    try:
        # =================================================
        # ASSESSMENT MODE
        # =================================================

        objective_mode = (
                page_data.assessment_mode
                in {
                    AssessmentMode.BY_OBJECTIVES.value,
                    AssessmentMode.ASSESSMENT_BY_SECTION.value,
                    AssessmentMode.ASSESSMENT_BY_QUARTER.value,
                }
        )

        if (
                page_data.assessment_mode
                not in {
                    AssessmentMode.WITHOUT_OBJECTIVES.value,
                    AssessmentMode.BY_OBJECTIVES.value,
                    AssessmentMode.ASSESSMENT_BY_SECTION.value,
                    AssessmentMode.ASSESSMENT_BY_QUARTER.value,
                }
        ):
            raise ValueError(
                "Неизвестный режим Assessment."
            )

        # =================================================
        # STUDENTS
        # =================================================

        for group in page_data.groups:

            for student in group.students:

                student_id = (
                    student
                    .assessment_student_id
                )

                # =========================================
                # PARTICIPATION STATUS
                # =========================================

                status_raw = str(
                    form.get(
                        f"status_{student_id}"
                    )
                    or AssessmentParticipationStatus
                    .ASSIGNED
                    .value
                ).strip()

                participation_status = (
                    AssessmentParticipationStatus(
                        status_raw
                    )
                )

                # =========================================
                # NOT COMPLETED
                # =========================================

                if (
                        participation_status
                        != AssessmentParticipationStatus
                        .COMPLETED
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
                # WITHOUT OBJECTIVES
                # =========================================

                if not objective_mode:
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

                    continue

                # =========================================
                # SECTION / QUARTER
                # =========================================

                objective_scores: list[
                    ManualObjectiveScoreDTO
                ] = []

                for objective in (
                        page_data.objectives
                ):
                    objective_id = (
                        objective
                        .assessment_objective_id
                    )

                    objective_score = (
                        _parse_decimal(
                            form.get(
                                "objective_score_"
                                f"{student_id}_"
                                f"{objective_id}"
                            ),
                            field_name=(
                                "Балл: "
                                f"{student.student_name} / "
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
                                objective_id
                            ),
                            score=(
                                objective_score
                            ),
                        )
                    )

                # -----------------------------------------
                # Итоговый score рассчитывает Service Layer
                # -----------------------------------------

                results.append(
                    ManualStudentResultDTO(
                        assessment_student_id=(
                            student_id
                        ),
                        participation_status=(
                            participation_status
                        ),
                        score=None,
                        objective_scores=tuple(
                            objective_scores
                        ),
                    )
                )

        # =================================================
        # SAVE DTO
        # =================================================

        dto = ManualAssessmentSaveDTO(
            assessment_id=assessment_id,
            results=tuple(
                results
            ),
        )

        # =================================================
        # SERVICE
        # =================================================

        await ManualAssessmentService.save_results(
            db,
            school_id=school_id,
            dto=dto,
        )

    except ValueError as exc:

        await db.rollback()

        # rollback() делает ORM user expired.
        await db.refresh(
            user
        )

        # После rollback заново получаем page data.
        page_data = (
            await ManualAssessmentService
            .get_manual_entry_page(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

        return render_error(
            templates,
            request,
            "staff/assessment/manual_entry.html",
            ctx={
                "user": user,

                "dto": page_data,

                "assessment": page_data,

                "groups": (
                    page_data.groups
                ),

                "participation_statuses": (
                    enum_items(
                        AssessmentParticipationStatus
                    )
                ),

                "back_url": str(
                    back_url
                ),

                "form_action": str(
                    form_action
                ),

                "create_url": str(
                    create_url
                ),
            },
            error=str(
                exc
            ),
            status_code=400,
        )

    # =====================================================
    # REDIRECT
    # =====================================================

    redirect_url = request.url_for(
        "staff_assessment_manual_page",
        assessment_id=assessment_id,
    )

    return RedirectResponse(
        url=(
            f"{redirect_url}"
            "?success=saved"
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
    name="staff_assessment_complete",
)
async def staff_assessment_complete(
        request: Request,
        assessment_id: int,

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_roles(
                UserRole.SCHOOL_ADMIN,
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Завершить Assessment текущей школы.

    AssessmentQualitySummary и статус COMPLETED
    сохраняются одной транзакцией
    в AssessmentCompletionService.
    """

    school_id = require_school_id(
        user
    )

    list_url = request.url_for(
        "staff_assessment_list_page"
    )

    try:
        await AssessmentCompletionService.complete_for_school(
            db,
            school_id=school_id,
            assessment_id=assessment_id,
        )

    except ValueError as exc:
        query = urlencode(
            {
                "error": str(exc),
            }
        )

        return RedirectResponse(
            url=f"{list_url}?{query}",
            status_code=(
                status.HTTP_303_SEE_OTHER
            ),
        )

    return RedirectResponse(
        url=(
            f"{list_url}"
            "?success=completed"
        ),
        status_code=(
            status.HTTP_303_SEE_OTHER
        ),
    )


# =========================================================
# SCHOOL ANALYTICS
# =========================================================


@router.get(
    "/analytics",
    name="staff_assessment_analytics_page",
    response_class=HTMLResponse,
)
async def staff_assessment_analytics_page(
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
            require_roles(
                UserRole.SCHOOL_ADMIN,
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Аналитика качества знаний текущей школы.

    Источник аналитики:
        AssessmentQualitySummary

    Показывает:
        - общий итог школы;
        - аналитику по классам;
        - реальные доступные фильтры.
    """

    # =====================================================
    # SECURITY BOUNDARY
    # =====================================================

    school_id = require_school_id(
        user
    )

    # =====================================================
    # AVAILABLE FILTERS
    # =====================================================

    filter_options = (
        await KnowledgeQualityAnalyticsService
        .get_school_filter_options(
            db,
            school_id=school_id,
        )
    )

    # =====================================================
    # NORMALIZE QUERY PARAMS
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
        selected_academic_year = None

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
    # SCHOOL TOTAL
    # =====================================================

    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='school', scope_id=school_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='')
    work_key = work_selection['work_key']
    all_rows = await KnowledgeQualityAnalyticsService.get_all_work_rows(
            db, scope='school', scope_id=school_id,
            academic_year_start=selected_academic_year, subject_id=selected_subject_id,
            grade_level=selected_grade_level, checkpoint=work_selection['checkpoint'], offset=(work_page-1)*50, limit=51) if work_key == 'all' else ()


    school_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_school_analytics(
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
            work_key=work_key,
        )
    )

    # =====================================================
    # SCHOOL -> CLASSES
    # =====================================================

    class_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_school_class_analytics(
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
            work_key=work_key,
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
        "staff/assessment/analytics.html",
        {
            "user": user,
            "work_selection": work_selection,
            "all_work_rows": all_rows[:50], "all_work_next": len(all_rows)>50, "work_page": work_page,
            "all_work_scope": 'school',

            # ---------------------------------------------
            # SCOPE
            # ---------------------------------------------

            "school_id": school_id,

            # ---------------------------------------------
            # ANALYTICS
            # ---------------------------------------------

            "dto": school_analytics,

            "school_analytics": (
                school_analytics
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


@router.get(
    "/analytics/export.xlsx",
    name="staff_assessment_analytics_export_excel",
)
async def staff_assessment_analytics_export_excel(
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
            require_roles(
                UserRole.SCHOOL_ADMIN,
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Excel-экспорт аналитики школы.

    school_id определяется только
    по текущему пользователю.
    """

    school_id = require_school_id(
        user
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

    selected_grade_level = (
        parse_optional_int(
            grade_level
        )
    )

    filter_options = await KnowledgeQualityAnalyticsRepo.get_school_filter_options(db, school_id=school_id)
    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='school', scope_id=school_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='')
    work_key = work_selection['work_key']

    if work_selection['selected'] is None:
        raise HTTPException(status_code=400, detail=work_selection['prompt'])

    dto = (
        await KnowledgeQualityExportService
        .build_school_export(
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
            work_key=work_key,
        )
    )

    dto = replace(dto, work_title=work_selection['selected']['label'])
    if work_key == 'all':
        all_rows = await KnowledgeQualityAnalyticsService.get_all_work_rows(
            db, scope='school', scope_id=school_id,
            academic_year_start=selected_academic_year, subject_id=selected_subject_id,
            grade_level=selected_grade_level, checkpoint=work_selection['checkpoint'], limit=50001)
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

    return excel_download_response(
        content=content,
        filename=(
            "bilim_sapasy_mektep.xlsx"
        ),
    )
