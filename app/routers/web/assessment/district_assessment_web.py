# app/routers/web/assessment/district_assessment_web.py

from __future__ import annotations
from app.modules.assessment.services.analytics_work_selection import prepare_work_selection, normalize_filters
from dataclasses import replace

from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.assessment.exporters.knowledge_quality_excel import KnowledgeQualityExcelExporter
from app.modules.assessment.repositories.knowledge_quality_analytics_repo import KnowledgeQualityAnalyticsRepo
from app.modules.assessment.services.knowledge_quality_analytics_service import (
    KnowledgeQualityAnalyticsService,
)
from app.modules.assessment.services.knowledge_quality_dynamics_service import KnowledgeQualityDynamicsService
from app.modules.assessment.services.knowledge_quality_export_service import KnowledgeQualityExportService
from app.modules.education.repositories.subject_repo import (
    SubjectRepo,
)
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.modules.users.deps import require_roles
from app.routers.web.assessment.helpers.export_response import excel_download_response
from app.routers.web.helpers.render import render
from app.routers.web.helpers.request import parse_optional_int
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/district/assessment",
    tags=["district-assessment"],
)


# =========================================================
# HELPERS
# =========================================================


def _academic_year_start() -> int:
    """
    Текущий учебный год.

    Август–декабрь:
        текущий год.

    Январь–июль:
        предыдущий год.
    """

    today = date.today()

    if today.month >= 8:
        return today.year

    return today.year - 1


def _require_district_id(
        user: User,
) -> int:
    """
    Получить district_id авторизованного
    районного пользователя.

    district_id никогда не принимается из URL/query,
    чтобы пользователь не мог запросить чужой район.
    """

    district_id = getattr(
        user,
        "district_id",
        None,
    )

    if district_id is None:
        raise ValueError(
            "Для пользователя не указан район."
        )

    return int(
        district_id
    )


# =========================================================
# DISTRICT ANALYTICS
# =========================================================


@router.get(
    "/analytics",
    name="district_assessment_analytics_page",
    response_class=HTMLResponse,
)
async def district_assessment_analytics_page(
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
                UserRole.DISTRICT_ADMIN,
            )
        ),
):
    """
    Аналитика Assessment районного уровня.

    Отображает:
        - общий итог района;
        - показатели качества знаний;
        - drill-down по школам.

    Фильтры:
        - учебный год;
        - предмет;
        - параллель.

    district_id берётся только из
    авторизованного пользователя.
    """

    # =====================================================
    # DISTRICT SECURITY BOUNDARY
    # =====================================================

    district_id = _require_district_id(
        user
    )

    filter_options = (
        await KnowledgeQualityAnalyticsRepo
        .get_district_filter_options(
            db,
            district_id=district_id,
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

    # -----------------------------------------------------
    # Academic year
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # Subject
    # -----------------------------------------------------

    if (
            selected_subject_id is not None
            and selected_subject_id
            not in filter_options.subject_ids
    ):
        selected_subject_id = None

    # -----------------------------------------------------
    # Grade level
    # -----------------------------------------------------

    if (
            selected_grade_level is not None
            and selected_grade_level
            not in filter_options.grade_levels
    ):
        selected_grade_level = None

    # =====================================================
    # DISTRICT TOTAL
    # =====================================================

    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='district', scope_id=district_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='')
    work_key = work_selection['work_key']
    all_rows = await KnowledgeQualityAnalyticsService.get_all_work_rows(
            db, scope='district', scope_id=district_id,
            academic_year_start=selected_academic_year, subject_id=selected_subject_id,
            grade_level=selected_grade_level, checkpoint=work_selection['checkpoint'], offset=(work_page-1)*50, limit=51) if work_key == 'all' else ()


    district_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_district_analytics(
            db,
            district_id=district_id,
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
    # DISTRICT -> SCHOOLS
    # =====================================================

    school_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_district_school_analytics(
            db,
            district_id=district_id,
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
    # FILTER OPTIONS
    # =====================================================

    academic_years = (
        filter_options.academic_years
    )

    subjects = (
        await SubjectRepo.get_active_by_ids(
            db,
            subject_ids=(
                filter_options.subject_ids
            ),
        )
    )

    grade_levels = (
        filter_options.grade_levels
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "district/assessment/analytics.html",
        {
            # ---------------------------------------------
            # USER / SCOPE
            # ---------------------------------------------

            "user": user,
            "work_selection": work_selection,
            "all_work_rows": all_rows[:50], "all_work_next": len(all_rows)>50, "work_page": work_page,
            "all_work_scope": 'district',

            "district_id": district_id,

            # ---------------------------------------------
            # ANALYTICS
            # ---------------------------------------------

            "dto": district_analytics,

            "district_analytics": (
                district_analytics
            ),

            "school_analytics": (
                school_analytics
            ),

            "schools": (
                school_analytics.items
            ),

            # ---------------------------------------------
            # FILTER OPTIONS
            # ---------------------------------------------

            "subjects": subjects,

            "grade_levels": (
                grade_levels
            ),

            "academic_years": (
                academic_years
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

            # ---------------------------------------------
            # OTHER
            # ---------------------------------------------

            "school_count": (
                school_analytics.item_count
            ),
        },
    )


# =========================================================
# DISTRICT KNOWLEDGE QUALITY DYNAMICS
# =========================================================


@router.get(
    "/dynamics",
    name="district_assessment_knowledge_quality_dynamics",
    response_class=HTMLResponse,
)
async def district_assessment_knowledge_quality_dynamics(
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

        db: AsyncSession = Depends(
            get_db
        ),

        user: User = Depends(
            require_roles(
                UserRole.DISTRICT_ADMIN,
            )
        ),
):
    """
    Динамика качества знаний районного уровня.

    Security boundary:
        district_id берётся только из
        авторизованного пользователя.

    Drill-down:
        district
            -> subject
            -> grade
            -> school

    Район не получает:
        - class;
        - teacher;
        - student.
    """

    # =====================================================
    # DISTRICT SECURITY BOUNDARY
    # =====================================================

    district_id = _require_district_id(
        user
    )

    # =====================================================
    # NORMALIZE QUERY PARAMS
    # =====================================================

    requested_academic_year = (
        parse_optional_int(
            academic_year_start
        )
    )

    requested_subject_id = (
        parse_optional_int(
            subject_id
        )
    )

    requested_grade_level = (
        parse_optional_int(
            grade_level
        )
    )

    # =====================================================
    # DYNAMICS FILTER OPTIONS
    # =====================================================

    filter_options = (
        await KnowledgeQualityDynamicsService
        .get_district_filter_options(
            db,
            district_id=district_id,

            academic_year_start=(
                requested_academic_year
            ),

            subject_id=(
                requested_subject_id
            ),

            grade_level=(
                requested_grade_level
            ),
        )
    )

    selected_academic_year = (
        filter_options.selected_academic_year
    )

    selected_subject_id = (
        filter_options.selected_subject_id
    )

    selected_grade_level = (
        filter_options.selected_grade_level
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
        if filter_options.subject_ids
        else []
    )

    # =====================================================
    # NO DYNAMICS DATA
    # =====================================================

    if selected_academic_year is None:
        return render(
            templates,
            request,
            "district/assessment/dynamics.html",
            {
                "user": user,
                "district_id": district_id,

                "district_dynamics": None,
                "school_dynamics": None,

                "schools": (),
                "school_count": 0,

                "subjects": subjects,

                "academic_years": (
                    filter_options.academic_years
                ),

                "grade_levels": (
                    filter_options.grade_levels
                ),

                "selected_academic_year": None,
                "selected_subject_id": None,
                "selected_grade_level": None,
            },
        )

    # =====================================================
    # DISTRICT TOTAL
    # =====================================================

    district_dynamics = (
        await KnowledgeQualityDynamicsService
        .get_district_dynamics(
            db,
            district_id=district_id,

            academic_year_start=(
                selected_academic_year
            ),

            subject_id=(
                selected_subject_id
            ),

            grade_level=(
                selected_grade_level
            ),
        )
    )

    # =====================================================
    # DISTRICT -> SCHOOLS
    # =====================================================

    school_dynamics = (
        await KnowledgeQualityDynamicsService
        .get_district_school_dynamics(
            db,
            district_id=district_id,

            academic_year_start=(
                selected_academic_year
            ),

            subject_id=(
                selected_subject_id
            ),

            grade_level=(
                selected_grade_level
            ),
        )
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "district/assessment/dynamics.html",
        {
            "user": user,

            # ---------------------------------------------
            # SCOPE
            # ---------------------------------------------

            "district_id": district_id,

            # ---------------------------------------------
            # DYNAMICS
            # ---------------------------------------------

            "district_dynamics": (
                district_dynamics
            ),

            "school_dynamics": (
                school_dynamics
            ),

            "schools": (
                school_dynamics.items
            ),

            "school_count": (
                school_dynamics.item_count
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
    name="district_assessment_analytics_export_excel",
)
async def district_assessment_analytics_export_excel(
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
                UserRole.DISTRICT_ADMIN,
            )
        ),
):
    """
    Excel-экспорт аналитики района.

    district_id определяется только
    по текущему пользователю.
    """

    district_id = _require_district_id(
        user
    )

    filter_options = (
        await KnowledgeQualityAnalyticsRepo
        .get_district_filter_options(
            db,
            district_id=district_id,
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

    selected_grade_level = (
        parse_optional_int(
            grade_level
        )
    )

    # ---------------------------------------------
    # Academic year
    # ---------------------------------------------

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

    # ---------------------------------------------
    # Subject
    # ---------------------------------------------

    if (
            selected_subject_id is not None
            and selected_subject_id
            not in filter_options.subject_ids
    ):
        selected_subject_id = None

    # ---------------------------------------------
    # Grade
    # ---------------------------------------------

    if (
            selected_grade_level is not None
            and selected_grade_level
            not in filter_options.grade_levels
    ):
        selected_grade_level = None

    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='district', scope_id=district_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='')
    work_key = work_selection['work_key']

    if work_selection['selected'] is None:
        raise HTTPException(status_code=400, detail=work_selection['prompt'])

    dto = (
        await KnowledgeQualityExportService
        .build_district_export(
            db,
            district_id=district_id,
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
            db, scope='district', scope_id=district_id,
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
            "bilim_sapasy_audan.xlsx"
        ),
    )
