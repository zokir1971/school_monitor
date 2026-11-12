# app/modules/assessment/services/assessment_quality_summary_service.py

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentGrade,
    AssessmentParticipationStatus,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentQualitySummary,
)
from app.modules.assessment.repositories.assessment_quality_summary_repo import (
    AssessmentQualitySummaryRepo,
)
from app.modules.assessment.services.knowledge_quality_calculator import (
    KnowledgeQualityCalculator,
)


class AssessmentQualitySummaryService:
    """
    Формирует аналитические snapshot-строки
    AssessmentQualitySummary.

    Source of truth:
        AssessmentStudent
            -> AssessmentResult

    Summary создаётся по каждой AssessmentGroup отдельно.
    """

    # =====================================================
    # PUBLIC
    # =====================================================

    @classmethod
    async def rebuild_for_assessment(
            cls,
            db: AsyncSession,
            *,
            assessment: Assessment,
            district_id_snapshot: int | None,
            region_id_snapshot: int | None,
    ) -> list[AssessmentQualitySummary]:
        """
        Полностью пересчитать summary одного Assessment.

        assessment.groups,
        group.students,
        participant.result

        должны быть заранее загружены.
        """

        groups = cast(
            list[AssessmentGroup],
            assessment.groups,
        )

        if not groups:
            raise ValueError(
                "Assessment не содержит групп."
            )

        summaries: list[
            AssessmentQualitySummary
        ] = []

        calculated_at = datetime.now(
            timezone.utc
        )

        for group in groups:
            summary = cls._build_group_summary(
                assessment=assessment,
                group=group,
                district_id_snapshot=(
                    district_id_snapshot
                ),
                region_id_snapshot=(
                    region_id_snapshot
                ),
                calculated_at=calculated_at,
            )

            summaries.append(
                summary
            )

        return (
            await AssessmentQualitySummaryRepo
            .replace_for_assessment(
                db,
                assessment_id=assessment.id,
                school_id=assessment.school_id,
                summaries=summaries,
            )
        )

    # =====================================================
    # GROUP SUMMARY
    # =====================================================

    @classmethod
    def _build_group_summary(
        cls,
        *,
        assessment: Assessment,
        group: AssessmentGroup,
        district_id_snapshot: int | None,
        region_id_snapshot: int | None,
        calculated_at: datetime,
    ) -> AssessmentQualitySummary:
        participants = list(
            group.students
        )

        total_students = len(
            participants
        )

        participated_students = 0

        absent_students = 0
        excused_students = 0
        not_completed_students = 0

        grade_5_count = 0
        grade_4_count = 0
        grade_3_count = 0
        grade_2_count = 0

        score_sum = Decimal("0")
        percent_sum = Decimal("0")

        # =================================================
        # PARTICIPANTS
        # =================================================

        for participant in participants:
            participation_status = (
                participant.participation_status
            )

            if (
                participation_status
                == AssessmentParticipationStatus.ABSENT
            ):
                absent_students += 1
                continue

            if (
                participation_status
                == AssessmentParticipationStatus.EXCUSED
            ):
                excused_students += 1
                continue

            if (
                participation_status
                == AssessmentParticipationStatus.NOT_COMPLETED
            ):
                not_completed_students += 1
                continue

            result = participant.result

            # COMPLETED без результата должен быть пойман
            # ещё в complete_assessment(), но здесь тоже
            # не допускаем тихое повреждение summary.
            if result is None:
                if (
                    participation_status
                    == AssessmentParticipationStatus.COMPLETED
                ):
                    raise ValueError(
                        "Обнаружен ученик со статусом COMPLETED "
                        "без AssessmentResult."
                    )

                continue

            participated_students += 1

            score_sum += result.score
            percent_sum += result.percent

            # =================================================
            # GRADES
            # =================================================

            if (
                result.grade
                == AssessmentGrade.EXCELLENT
            ):
                grade_5_count += 1

            elif (
                result.grade
                == AssessmentGrade.GOOD
            ):
                grade_4_count += 1

            elif (
                result.grade
                == AssessmentGrade.SATISFACTORY
            ):
                grade_3_count += 1

            elif (
                result.grade
                == AssessmentGrade.UNSATISFACTORY
            ):
                grade_2_count += 1

            else:
                raise ValueError(
                    "Неизвестная оценка AssessmentResult."
                )

        # =================================================
        # CALCULATOR
        # =================================================

        metrics = (
            KnowledgeQualityCalculator.calculate(
                total_students=total_students,
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
        # SUMMARY ORM
        # =================================================

        return AssessmentQualitySummary(
            school_id=assessment.school_id,
            assessment_id=assessment.id,
            assessment_group_id=group.id,

            school_class_id=(
                group.school_class_id
            ),

            subject_id=(
                assessment.subject_id
            ),

            # =================================================
            # ORGANIZATION SNAPSHOT
            # =================================================

            teacher_staff_member_id_snapshot=(
                group.teacher_staff_member_id
            ),

            teacher_name_snapshot=(
                group.teacher_name_snapshot
            ),

            district_id_snapshot=(
                district_id_snapshot
            ),

            region_id_snapshot=(
                region_id_snapshot
            ),

            # =================================================
            # CLASS / PERIOD SNAPSHOT
            # =================================================

            class_name_snapshot=(
                group.class_name_snapshot
            ),

            grade_level_snapshot=(
                group.grade_level_snapshot
            ),

            academic_year_start_snapshot=(
                group.academic_year_start_snapshot
            ),

            checkpoint_snapshot=(
                assessment.checkpoint
            ),

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

            score_sum=(
                score_sum
            ),
            percent_sum=(
                percent_sum
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

            calculated_at=(
                calculated_at
            ),
        )
