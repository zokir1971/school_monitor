# app/routers/web/assessment/knowledge_quality_dynamics_web.py

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Request,
)
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.assessment.services.knowledge_quality_dynamics_service import (
    KnowledgeQualityDynamicsService,
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
from app.routers.web.helpers.render import render
from app.routers.web.helpers.request import parse_optional_int
from app.routers.web.web_common import templates


router = APIRouter(
    prefix="/staff/assessment",
    tags=["assessment-dynamics"],
)


@router.get(
    "/dynamics",
    name="staff_assessment_knowledge_quality_dynamics",
    response_class=HTMLResponse,
)
async def staff_assessment_knowledge_quality_dynamics(
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
                UserRole.SCHOOL_ADMIN,
                UserRole.SCHOOL_STAFF,
            )
        ),
):
    """
    Динамика качества знаний текущей школы
    внутри одного учебного года.

    Security boundary:
        school_id берётся только из текущего пользователя.

    Фильтры:
        - учебный год;
        - предмет;
        - параллель.

    Источник данных:
        AssessmentQualitySummary,
        только checkpoint_snapshot IS NOT NULL.

    Drill-down:
        school
            -> classes

    Важно:
        route не выполняет SQL внутри циклов.
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
        .get_school_filter_options(
            db,
            school_id=school_id,
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
            "staff/assessment/dynamics.html",
            {
                "user": user,
                "school_id": school_id,

                "school_dynamics": None,
                "class_dynamics": None,
                "classes": (),
                "class_count": 0,

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
    # SCHOOL DYNAMICS
    # =====================================================

    school_dynamics = (
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
        )
    )

    # =====================================================
    # SCHOOL -> CLASSES
    # =====================================================

    class_dynamics = (
        await KnowledgeQualityDynamicsService
        .get_school_class_dynamics(
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
        )
    )

    # =====================================================
    # RENDER
    # =====================================================

    return render(
        templates,
        request,
        "staff/assessment/dynamics.html",
        {
            "user": user,

            # ---------------------------------------------
            # SCOPE
            # ---------------------------------------------

            "school_id": school_id,

            # ---------------------------------------------
            # DYNAMICS
            # ---------------------------------------------

            "school_dynamics": (
                school_dynamics
            ),

            "class_dynamics": (
                class_dynamics
            ),

            "classes": (
                class_dynamics.items
            ),

            "class_count": (
                class_dynamics.item_count
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
