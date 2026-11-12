# app/modules/assessment/services/knowledge_quality_service.py

from __future__ import annotations
from app.modules.assessment.helpers.assessment_names import localized

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.repositories.assessment_quality_summary_repo import (
    AssessmentQualitySummaryRepo,
)
from app.modules.assessment.repositories.assessment_repo import (
    AssessmentRepo,
)
from app.modules.assessment.schemas.knowledge_quality_schemas import (
    KnowledgeQualityAssessmentDTO,
    KnowledgeQualityClassDTO,
)
from app.modules.assessment.services.knowledge_quality_calculator import (
    KnowledgeQualityCalculator,
)


class KnowledgeQualityService:
    """
    Аналитика качества знаний одного Assessment.

    Работает через AssessmentQualitySummary.

    Детальные AssessmentResult повторно не загружаются.
    """

    # =====================================================
    # PUBLIC
    # =====================================================

    @classmethod
    async def get_assessment_analytics(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        assessment_id: int,
    ) -> KnowledgeQualityAssessmentDTO:
        """
        Получить:
            - аналитику по каждому классу;
            - общий взвешенный итог Assessment.
        """

        # -------------------------------------------------
        # Assessment metadata
        # -------------------------------------------------

        assessment = (
            await AssessmentRepo.get_by_id_for_school(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

        if assessment is None:
            raise ValueError(
                "Assessment не найден."
            )

        # -------------------------------------------------
        # Summary rows
        # -------------------------------------------------

        summaries = (
            await AssessmentQualitySummaryRepo
            .get_by_assessment_id(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

        if not summaries:
            raise ValueError(
                "Для Assessment аналитические данные "
                "ещё не сформированы."
            )

        # =================================================
        # CLASS DTOs
        # =================================================

        class_dtos: list[
            KnowledgeQualityClassDTO
        ] = []

        for summary in summaries:
            class_dtos.append(
                KnowledgeQualityClassDTO(
                    assessment_group_id=(
                        summary.assessment_group_id
                    ),
                    school_class_id=(
                        summary.school_class_id
                    ),

                    class_name=(
                        summary.class_name_snapshot
                    ),
                    grade_level=(
                        summary.grade_level_snapshot
                    ),
                    academic_year_start=(
                        summary
                        .academic_year_start_snapshot
                    ),

                    total_students=(
                        summary.total_students
                    ),
                    participated_students=(
                        summary.participated_students
                    ),

                    absent_students=(
                        summary.absent_students
                    ),
                    excused_students=(
                        summary.excused_students
                    ),
                    not_completed_students=(
                        summary.not_completed_students
                    ),

                    grade_5_count=(
                        summary.grade_5_count
                    ),
                    grade_4_count=(
                        summary.grade_4_count
                    ),
                    grade_3_count=(
                        summary.grade_3_count
                    ),
                    grade_2_count=(
                        summary.grade_2_count
                    ),

                    average_score=(
                        summary.average_score
                    ),
                    average_percent=(
                        summary.average_percent
                    ),

                    achievement_percent=(
                        summary.achievement_percent
                    ),
                    quality_percent=(
                        summary.quality_percent
                    ),
                )
            )

        # =================================================
        # AGGREGATED COUNTS
        # =================================================

        total_students = sum(
            item.total_students
            for item in summaries
        )

        participated_students = sum(
            item.participated_students
            for item in summaries
        )

        absent_students = sum(
            item.absent_students
            for item in summaries
        )

        excused_students = sum(
            item.excused_students
            for item in summaries
        )

        not_completed_students = sum(
            item.not_completed_students
            for item in summaries
        )

        grade_5_count = sum(
            item.grade_5_count
            for item in summaries
        )

        grade_4_count = sum(
            item.grade_4_count
            for item in summaries
        )

        grade_3_count = sum(
            item.grade_3_count
            for item in summaries
        )

        grade_2_count = sum(
            item.grade_2_count
            for item in summaries
        )

        score_sum = sum(
            (
                item.score_sum
                for item in summaries
            ),
            Decimal("0"),
        )

        percent_sum = sum(
            (
                item.percent_sum
                for item in summaries
            ),
            Decimal("0"),
        )

        # =================================================
        # WEIGHTED TOTAL METRICS
        # =================================================

        metrics = (
            KnowledgeQualityCalculator.calculate(
                total_students=(
                    total_students
                ),
                participated_students=(
                    participated_students
                ),

                absent_students=(
                    absent_students
                ),
                excused_students=(
                    excused_students
                ),
                not_completed_students=(
                    not_completed_students
                ),

                grade_5_count=(
                    grade_5_count
                ),
                grade_4_count=(
                    grade_4_count
                ),
                grade_3_count=(
                    grade_3_count
                ),
                grade_2_count=(
                    grade_2_count
                ),

                score_sum=score_sum,
                percent_sum=percent_sum,
            )
        )

        # =================================================
        # RESULT
        # =================================================

        return KnowledgeQualityAssessmentDTO(
            assessment_id=assessment.id,

            title=localized(assessment),

            subject_id=assessment.subject_id,
            subject_name=(
                assessment.subject_name_snapshot
                or "—"
            ),

            assessment_type=(
                assessment.assessment_type.value
            ),
            assessment_type_label=(
                assessment.assessment_type.label_kz
            ),

            status=assessment.status.value,
            status_label=(
                assessment.status.label_kz
            ),

            max_score=assessment.max_score,

            total_students=(
                total_students
            ),
            participated_students=(
                participated_students
            ),

            absent_students=(
                absent_students
            ),
            excused_students=(
                excused_students
            ),
            not_completed_students=(
                not_completed_students
            ),

            grade_5_count=(
                grade_5_count
            ),
            grade_4_count=(
                grade_4_count
            ),
            grade_3_count=(
                grade_3_count
            ),
            grade_2_count=(
                grade_2_count
            ),

            average_score=(
                metrics.average_score
            ),
            average_percent=(
                metrics.average_percent
            ),

            achievement_percent=(
                metrics.achievement_percent
            ),
            quality_percent=(
                metrics.quality_percent
            ),

            classes=tuple(
                class_dtos
            ),
        )
