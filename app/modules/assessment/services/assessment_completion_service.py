# app/modules/assessment/services/assessment_completion_service.py

from __future__ import annotations

from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentParticipationStatus,
    AssessmentStatus,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentStudent,
)
from app.modules.assessment.repositories.assessment_repo import (
    AssessmentRepo,
)
from app.modules.assessment.services.assessment_quality_summary_service import (
    AssessmentQualitySummaryService,
)


class AssessmentCompletionService:
    """
    Завершение Assessment.

    Отвечает за:
        - проверку доступа;
        - проверку готовности результатов;
        - создание AssessmentQualitySummary;
        - перевод Assessment в COMPLETED;
        - единую транзакцию summary + status.

    Не используется аналитическими сервисами,
    поэтому циклической зависимости нет.
    """

    _FINAL_PARTICIPATION_STATUSES = frozenset(
        {
            AssessmentParticipationStatus.COMPLETED,
            AssessmentParticipationStatus.ABSENT,
            AssessmentParticipationStatus.EXCUSED,
            AssessmentParticipationStatus.NOT_COMPLETED,
        }
    )

    # =========================================================
    # SCHOOL
    # =========================================================

    @classmethod
    async def complete_for_school(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            assessment_id: int,
    ) -> None:
        """
        Завершить Assessment от имени школы.

        Scope:
            Assessment.school_id == school_id
        """

        cls._validate_ids(
            school_id=school_id,
            assessment_id=assessment_id,
        )

        assessment = (
            await AssessmentRepo.get_for_completion(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

        if assessment is None:
            raise ValueError(
                "Assessment не найден."
            )

        await cls._complete(
            db,
            assessment=assessment,
            school_id=school_id,
        )

    # =========================================================
    # TEACHER
    # =========================================================

    @classmethod
    async def complete_for_teacher(
            cls,
            db: AsyncSession,
            *,
            school_id: int,
            teacher_staff_member_id: int,
            assessment_id: int,
    ) -> None:
        """
        Завершить Assessment текущим учителем.

        Учителю недостаточно иметь хотя бы одну группу.

        Завершение разрешается только если:
            ВСЕ AssessmentGroup данного Assessment
            принадлежат текущему учителю.

        Это важно, потому что COMPLETED запускает создание
        AssessmentQualitySummary для школьной, районной
        и региональной аналитики.
        """

        cls._validate_ids(
            school_id=school_id,
            assessment_id=assessment_id,
        )

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "Некорректный teacher_staff_member_id."
            )

        owns_all_groups = (
            await AssessmentRepo.teacher_owns_all_groups(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
                teacher_staff_member_id=(
                    teacher_staff_member_id
                ),
            )
        )

        if not owns_all_groups:
            raise ValueError(
                "Assessment недоступен для завершения "
                "текущему учителю."
            )

        # После проверки ownership загружаем ПОЛНЫЙ Assessment.
        #
        # Не используем get_for_teacher_manual_entry(),
        # потому что его loader criteria намеренно ограничивает
        # assessment.groups группами текущего учителя.
        #
        # Для формирования итогового summary необходим
        # полный graph Assessment.
        assessment = (
            await AssessmentRepo.get_for_completion(
                db,
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

        if assessment is None:
            raise ValueError(
                "Assessment не найден."
            )

        await cls._complete(
            db,
            assessment=assessment,
            school_id=school_id,
        )

    # =========================================================
    # INTERNAL COMPLETE
    # =========================================================

    @classmethod
    async def _complete(
            cls,
            db: AsyncSession,
            *,
            assessment: Assessment,
            school_id: int,
    ) -> None:
        """
        Общая логика завершения.

        В этот метод поступает уже загруженный полный
        Assessment ORM graph.

        Никаких SQL-запросов внутри participant loop нет.
        """

        if getattr(assessment,'diagnostic_subject_id',None) is not None:
            raise ValueError('Завершайте онлайн-оценивание через страницу диагностической сессии.')
        cls._validate_assessment(
            assessment
        )

        participants = cls._collect_participants(
            assessment
        )

        cls._validate_participants(
            assessment=assessment,
            participants=participants,
        )

        org_snapshot = (
            await AssessmentRepo.get_school_org_snapshot(
                db,
                school_id=school_id,
            )
        )

        if org_snapshot is None:
            raise ValueError(
                "Не удалось определить школу "
                "для аналитического snapshot."
            )

        district_id_snapshot = (
            org_snapshot.district_id
        )

        region_id_snapshot = (
            org_snapshot.region_id
        )

        try:
            # =================================================
            # 1. QUALITY SUMMARY
            # =================================================

            await AssessmentQualitySummaryService.rebuild_for_assessment(
                db,
                assessment=assessment,
                district_id_snapshot=(
                    district_id_snapshot
                ),
                region_id_snapshot=(
                    region_id_snapshot
                ),
            )

            # =================================================
            # 2. STATUS
            # =================================================

            assessment.status = (
                AssessmentStatus.COMPLETED
            )

            await db.flush()

            # =================================================
            # 3. ONE TRANSACTION
            # =================================================

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    @classmethod
    def prepare_diagnostic_completion(cls, *, assessments, district_id_snapshot,
                                      region_id_snapshot, calculated_at):
        """Validate a preloaded school batch and build existing summary objects.

        The repository writes summaries and COMPLETED atomically in the caller's
        transaction. No per-assessment commit and no SQL inside these loops.
        """
        summaries=[]
        for assessment in assessments:
            if not getattr(assessment,'diagnostic_subject_id',None):
                raise ValueError('Diagnostic context required.')
            if assessment.status != AssessmentStatus.COMPLETED:
                cls._validate_assessment(assessment)
            participants=cls._collect_participants(assessment)
            cls._validate_participants(assessment=assessment,participants=participants)
            for group in assessment.groups:
                summaries.append(AssessmentQualitySummaryService._build_group_summary(
                    assessment=assessment,group=group,district_id_snapshot=district_id_snapshot,
                    region_id_snapshot=region_id_snapshot,calculated_at=calculated_at))
        return summaries

    # =========================================================
    # ASSESSMENT VALIDATION
    # =========================================================

    @staticmethod
    def _validate_assessment(
            assessment: Assessment,
    ) -> None:
        if (
                assessment.status
                == AssessmentStatus.COMPLETED
        ):
            raise ValueError(
                "Assessment уже завершён."
            )

        if (
                assessment.status
                == AssessmentStatus.ARCHIVED
        ):
            raise ValueError(
                "Архивный Assessment изменить нельзя."
            )

        if (
                assessment.max_score is None
                or assessment.max_score <= 0
        ):
            raise ValueError(
                "Перед завершением необходимо "
                "указать максимальный балл."
            )

    # =========================================================
    # PARTICIPANTS
    # =========================================================

    @staticmethod
    def _collect_participants(
            assessment: Assessment,
    ) -> tuple[
        AssessmentStudent,
        ...
    ]:
        """
        Собрать участников из заранее eager-loaded graph.

        Здесь не выполняются запросы к БД.
        """

        participants = tuple(
            participant
            for group in assessment.groups
            for participant in group.students
        )

        if not participants:
            raise ValueError(
                "Assessment не содержит участников."
            )

        return participants

    @classmethod
    def _validate_participants(
            cls,
            *,
            assessment: Assessment,
            participants: Iterable[
                AssessmentStudent
            ],
    ) -> None:
        """
        Проверить готовность всех участников.

        participant.result должен быть eager-loaded
        методом AssessmentRepo.get_for_completion().

        SQL внутри цикла отсутствует.
        """

        unfinished_names: list[str] = []
        missing_results: list[str] = []
        invalid_results: list[str] = []

        for participant in participants:
            participation_status = (
                cls._normalize_participation_status(
                    participant.participation_status
                )
            )

            student_name = (
                participant.student_name_snapshot
                or f"ID {participant.student_id}"
            )

            # =================================================
            # FINAL STATUS
            # =================================================

            if (
                    participation_status is None
                    or participation_status
                    not in cls._FINAL_PARTICIPATION_STATUSES
            ):
                unfinished_names.append(
                    student_name
                )
                continue

            # =================================================
            # COMPLETED RESULT
            # =================================================

            if (
                    participation_status
                    != AssessmentParticipationStatus.COMPLETED
            ):
                continue

            result = participant.result

            if result is None:
                missing_results.append(
                    student_name
                )
                continue

            if (
                    result.max_score <= 0
                    or result.max_score != assessment.max_score
                    or result.score < 0
                    or result.score > result.max_score
                    or result.percent < 0
                    or result.percent > 100
            ):
                invalid_results.append(
                    student_name
                )

        # =====================================================
        # VALIDATION ERRORS
        # =====================================================

        if unfinished_names:
            raise ValueError(
                "Нәтижесі әлі енгізілмеген оқушылар бар: "
                + ", ".join(
                    unfinished_names
                )
            )

        if missing_results:
            raise ValueError(
                "«Орындалды» күйіндегі оқушылардың "
                "нәтижесі жоқ: "
                + ", ".join(
                    missing_results
                )
            )

        if invalid_results:
            raise ValueError(
                "Некорректный балл обнаружен у учеников: "
                + ", ".join(
                    invalid_results
                )
            )

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _normalize_participation_status(
            raw_status,
    ) -> AssessmentParticipationStatus | None:
        if isinstance(
                raw_status,
                AssessmentParticipationStatus,
        ):
            return raw_status

        try:
            return AssessmentParticipationStatus(
                str(raw_status)
            )
        except ValueError:
            return None

    @staticmethod
    def _validate_ids(
            *,
            school_id: int,
            assessment_id: int,
    ) -> None:
        if school_id <= 0:
            raise ValueError(
                "Некорректный school_id."
            )

        if assessment_id <= 0:
            raise ValueError(
                "Некорректный assessment_id."
            )
