# app/routers/web/assessment/region_assessment_web.py

from __future__ import annotations
from app.modules.assessment.services.analytics_work_selection import prepare_work_selection, normalize_filters
from dataclasses import replace

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
from app.modules.assessment.repositories.knowledge_quality_analytics_repo import (
    KnowledgeQualityAnalyticsRepo,
)
from app.modules.assessment.services.knowledge_quality_analytics_service import (
    KnowledgeQualityAnalyticsService,
)
from app.modules.assessment.services.knowledge_quality_dynamics_service import KnowledgeQualityDynamicsService
from app.modules.assessment.services.knowledge_quality_export_service import KnowledgeQualityExportService
from app.modules.education.repositories.subject_repo import (
    SubjectRepo,
)
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.assessment.helpers.export_response import excel_download_response
from app.routers.web.helpers.render import render
from app.routers.web.helpers.request import parse_optional_int
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/region/assessment",
    tags=["region-assessment"],
)


# =========================================================
# HELPERS
# =========================================================


def _require_region_id(
    user: User,
) -> int:
    """
    Получить region_id текущего регионального пользователя.

    region_id не принимается из URL/query:
    региональная граница определяется только сервером.
    """

    region_id = getattr(
        user,
        "region_id",
        None,
    )

    if region_id is None:
        raise ValueError(
            "Для пользователя не указан регион."
        )

    return int(
        region_id
    )


# =========================================================
# REGION ANALYTICS
# =========================================================


@router.get(
    "/analytics",
    name="region_assessment_analytics_page",
    response_class=HTMLResponse,
)
async def region_assessment_analytics_page(
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
            UserRole.REGION_ADMIN,
        )
    ),
):
    """
    Региональная аналитика Assessment.

    Показывает:
        - общий итог региона;
        - drill-down по районам.

    Фильтры основаны только на реальных
    AssessmentQualitySummary.
    """

    # =====================================================
    # REGION SECURITY BOUNDARY
    # =====================================================

    region_id = _require_region_id(
        user
    )

    # =====================================================
    # AVAILABLE FILTERS
    # =====================================================

    filter_options = (
        await KnowledgeQualityAnalyticsRepo
        .get_region_filter_options(
            db,
            region_id=region_id,
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
    # Grade
    # -----------------------------------------------------

    if (
        selected_grade_level is not None
        and selected_grade_level
        not in filter_options.grade_levels
    ):
        selected_grade_level = None

    # =====================================================
    # REGION TOTAL
    # =====================================================

    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='region', scope_id=region_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='')
    work_key = work_selection['work_key']
    all_rows = await KnowledgeQualityAnalyticsService.get_all_work_rows(
            db, scope='region', scope_id=region_id,
            academic_year_start=selected_academic_year, subject_id=selected_subject_id,
            grade_level=selected_grade_level, checkpoint=work_selection['checkpoint'], offset=(work_page-1)*50, limit=51) if work_key == 'all' else ()


    region_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_region_analytics(
            db,
            region_id=region_id,
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
    # REGION -> DISTRICTS
    # =====================================================

    district_analytics = (
        await KnowledgeQualityAnalyticsService
        .get_region_district_analytics(
            db,
            region_id=region_id,
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

    subjects = (
        await SubjectRepo.get_active_by_ids(
            db,
            subject_ids=(
                filter_options.subject_ids
            ),
        )
    )

    academic_years = (
        filter_options.academic_years
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
        "region/assessment/analytics.html",
        {
            "user": user,
            "work_selection": work_selection,
            "all_work_rows": all_rows[:50], "all_work_next": len(all_rows)>50, "work_page": work_page,
            "all_work_scope": 'region',

            # ---------------------------------------------
            # SCOPE
            # ---------------------------------------------

            "region_id": region_id,

            # ---------------------------------------------
            # ANALYTICS
            # ---------------------------------------------

            "dto": region_analytics,

            "region_analytics": (
                region_analytics
            ),

            "district_analytics": (
                district_analytics
            ),

            "districts": (
                district_analytics.items
            ),

            "district_count": (
                district_analytics.item_count
            ),

            # ---------------------------------------------
            # FILTER OPTIONS
            # ---------------------------------------------

            "subjects": subjects,

            "academic_years": (
                academic_years
            ),

            "grade_levels": (
                grade_levels
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
# REGION KNOWLEDGE QUALITY DYNAMICS
# =========================================================


@router.get(
    "/dynamics",
    name="region_assessment_knowledge_quality_dynamics",
    response_class=HTMLResponse,
)
async def region_assessment_knowledge_quality_dynamics(
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

    district_id: str | None = Query(
        default=None,
    ),

    db: AsyncSession = Depends(
        get_db
    ),

    user: User = Depends(
        require_roles(
            UserRole.REGION_ADMIN,
        )
    ),
):
    """
    Динамика качества знаний регионального уровня.

    Security boundary:
        region_id берётся только из
        авторизованного пользователя.

    Drill-down:
        region
            -> subject
            -> grade
            -> district
            -> school

    Регион не получает:
        - class;
        - teacher;
        - student.
    """

    # =====================================================
    # REGION SECURITY BOUNDARY
    # =====================================================

    region_id = _require_region_id(
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

    requested_district_id = (
        parse_optional_int(
            district_id
        )
    )

    # =====================================================
    # DYNAMICS FILTER OPTIONS
    # =====================================================

    filter_options = (
        await KnowledgeQualityDynamicsService
        .get_region_filter_options(
            db,
            region_id=region_id,

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
            "region/assessment/dynamics.html",
            {
                "user": user,

                "region_id": region_id,

                "region_dynamics": None,
                "district_dynamics": None,
                "school_dynamics": None,

                "districts": (),
                "schools": (),

                "district_count": 0,
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
                "selected_district_id": None,
            },
        )

    # =====================================================
    # REGION TOTAL
    # =====================================================

    region_dynamics = (
        await KnowledgeQualityDynamicsService
        .get_region_dynamics(
            db,
            region_id=region_id,

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
    # REGION -> DISTRICTS
    # =====================================================

    district_dynamics = (
        await KnowledgeQualityDynamicsService
        .get_region_district_dynamics(
            db,
            region_id=region_id,

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

    districts = (
        district_dynamics.items
    )

    # =====================================================
    # VALIDATE SELECTED DISTRICT
    # =====================================================

    available_district_ids = {
        item.entity_id
        for item in districts
    }

    selected_district_id = (
        requested_district_id
        if (
            requested_district_id
            in available_district_ids
        )
        else None
    )

    # =====================================================
    # REGION -> DISTRICT -> SCHOOLS
    # =====================================================

    school_dynamics = None
    schools = ()
    school_count = 0

    if selected_district_id is not None:

        school_dynamics = (
            await KnowledgeQualityDynamicsService
            .get_region_school_dynamics(
                db,

                region_id=region_id,

                district_id=(
                    selected_district_id
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
            )
        )

        schools = (
            school_dynamics.items
        )

        school_count = (
            school_dynamics.item_count
        )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "region/assessment/dynamics.html",
        {
            "user": user,

            # ---------------------------------------------
            # SCOPE
            # ---------------------------------------------

            "region_id": region_id,

            # ---------------------------------------------
            # DYNAMICS
            # ---------------------------------------------

            "region_dynamics": (
                region_dynamics
            ),

            "district_dynamics": (
                district_dynamics
            ),

            "school_dynamics": (
                school_dynamics
            ),

            "districts": (
                districts
            ),

            "schools": (
                schools
            ),

            "district_count": (
                district_dynamics.item_count
            ),

            "school_count": (
                school_count
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

            "selected_district_id": (
                selected_district_id
            ),
        },
    )


@router.get(
    "/analytics/export.xlsx",
    name="region_assessment_analytics_export_excel",
)
async def region_assessment_analytics_export_excel(
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
            UserRole.REGION_ADMIN,
        )
    ),
):
    """
    Excel-экспорт аналитики региона.

    region_id определяется только
    по текущему пользователю.
    """

    region_id = _require_region_id(
        user
    )

    filter_options = (
        await KnowledgeQualityAnalyticsRepo
        .get_region_filter_options(
            db,
            region_id=region_id,
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

    if (
        selected_subject_id is not None
        and selected_subject_id
        not in filter_options.subject_ids
    ):
        selected_subject_id = None

    if (
        selected_grade_level is not None
        and selected_grade_level
        not in filter_options.grade_levels
    ):
        selected_grade_level = None

    selected_academic_year, selected_subject_id, selected_grade_level = normalize_filters(
        filter_options, parse_optional_int(academic_year_start), parse_optional_int(subject_id), parse_optional_int(grade_level))
    work_selection = await prepare_work_selection(
        db, scope='region', scope_id=region_id,
        academic_year_start=selected_academic_year, subject_id=selected_subject_id,
        grade_level=selected_grade_level, work_key=work_key, checkpoint=checkpoint,
        search='')
    work_key = work_selection['work_key']

    if work_selection['selected'] is None:
        raise HTTPException(status_code=400, detail=work_selection['prompt'])

    dto = (
        await KnowledgeQualityExportService
        .build_region_export(
            db,
            region_id=region_id,
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
            db, scope='region', scope_id=region_id,
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
            "bilim_sapasy_onir.xlsx"
        ),
    )
