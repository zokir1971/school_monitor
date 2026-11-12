# app/modules/assessment/services/assessment_manual_grading_service.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentAnswerStatus,
    AssessmentParticipationStatus,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentStudent,
)
from app.modules.assessment.repositories.assessment_student_answer_repo import (
    AssessmentStudentAnswerRepo,
)
from app.modules.assessment.repositories.teacher_assessment_result_repo import (
    TeacherAssessmentResultRepo,
)
from app.modules.assessment.services.assessment_grading_service import (
    AssessmentGradingService,
)


@dataclass(frozen=True, slots=True)
class AssessmentManualGradingResult:
    """
    Результат ручной проверки одного ответа учителем.
    """

    assessment_id: int
    assessment_student_id: int
    assessment_student_answer_id: int

    answer_status: str
    score: Decimal
    max_score: Decimal

    participation_status: str
    has_pending_review: bool
    completed_at: datetime | None


class AssessmentManualGradingService:
    """
    Ручная проверка отдельных ответов ONLINE Assessment.

    Ответственность:
        - teacher security boundary;
        - проверка PENDING_REVIEW ответа;
        - сохранение выставленного балла;
        - фиксация проверяющего пользователя;
        - определение наличия оставшихся PENDING_REVIEW;
        - финализация AssessmentResult после последнего ручного ответа;
        - перевод участника SUBMITTED -> COMPLETED.

    Сервис владеет транзакцией:
        commit / rollback выполняются здесь.
    """

    @classmethod
    async def grade_answer(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        teacher_staff_member_id: int,
        checked_by_user_id: int,
        assessment_student_answer_id: int,
        score: Decimal,
    ) -> AssessmentManualGradingResult:
        cls._validate_ids(
            school_id=school_id,
            teacher_staff_member_id=teacher_staff_member_id,
            checked_by_user_id=checked_by_user_id,
            assessment_student_answer_id=assessment_student_answer_id,
        )

        answer = (
            await TeacherAssessmentResultRepo
            .get_teacher_answer_for_review(
                db,
                school_id=school_id,
                teacher_staff_member_id=teacher_staff_member_id,
                assessment_student_answer_id=(
                    assessment_student_answer_id
                ),
            )
        )

        if answer is None:
            raise ValueError(
                "Жауап табылмады немесе оны тексеруге рұқсат жоқ."
            )

        participant = cast(
            AssessmentStudent,
            answer.assessment_student,
        )

        assessment = cast(
            Assessment,
            participant.assessment_group.assessment,
        )

        cls._validate_review_state(
            assessment=assessment,
            participant=participant,
            answer_status=answer.status,
            school_id=school_id,
        )

        max_score = cast(
            Decimal,
            answer.max_score,
        )

        cls._validate_score(
            score=score,
            max_score=max_score,
        )

        checked_at = cls._utc_now()

        try:
            answer.score = score
            answer.max_score = max_score

            # Для ручной проверки is_correct означает получение
            # полного балла за ответ.
            answer.is_correct = score == max_score

            answer.status = AssessmentAnswerStatus.CHECKED
            answer.checked_by_user_id = checked_by_user_id
            answer.checked_at = checked_at

            await db.flush()

            answers = (
                await AssessmentStudentAnswerRepo
                .get_many_for_student(
                    db,
                    assessment_student_id=participant.id,
                )
            )

            has_pending_review = any(
                item.status
                == AssessmentAnswerStatus.PENDING_REVIEW
                for item in answers
            )

            if has_pending_review:
                participant.participation_status = (
                    AssessmentParticipationStatus.SUBMITTED
                )
                participant.completed_at = None

                await db.flush()
                await db.commit()

                return cls._build_result(
                    assessment=assessment,
                    participant=participant,
                    assessment_student_answer_id=answer.id,
                    score=score,
                    max_score=max_score,
                    has_pending_review=True,
                )

            await AssessmentGradingService.finalize_student_result(
                db,
                assessment=assessment,
                participant=participant,
                calculated_at=checked_at,
            )

            participant.participation_status = (
                AssessmentParticipationStatus.COMPLETED
            )
            participant.completed_at = checked_at

            await db.flush()
            await db.commit()

            return cls._build_result(
                assessment=assessment,
                participant=participant,
                assessment_student_answer_id=answer.id,
                score=score,
                max_score=max_score,
                has_pending_review=False,
            )

        except Exception:
            await db.rollback()
            raise

    @staticmethod
    def _validate_ids(
        *,
        school_id: int,
        teacher_staff_member_id: int,
        checked_by_user_id: int,
        assessment_student_answer_id: int,
    ) -> None:
        if school_id <= 0:
            raise ValueError("Некорректный school_id.")

        if teacher_staff_member_id <= 0:
            raise ValueError(
                "Некорректный teacher_staff_member_id."
            )

        if checked_by_user_id <= 0:
            raise ValueError(
                "Некорректный checked_by_user_id."
            )

        if assessment_student_answer_id <= 0:
            raise ValueError(
                "Некорректный assessment_student_answer_id."
            )

    @staticmethod
    def _validate_review_state(
        *,
        assessment: Assessment,
        participant: AssessmentStudent,
        answer_status: AssessmentAnswerStatus,
        school_id: int,
    ) -> None:
        if assessment.school_id != school_id:
            raise ValueError(
                "Assessment басқа мектепке тиесілі."
            )

        if participant.school_id != school_id:
            raise ValueError(
                "Assessment қатысушысы басқа мектепке тиесілі."
            )

        if (
            participant.participation_status
            != AssessmentParticipationStatus.SUBMITTED
        ):
            raise ValueError(
                "Жауапты қолмен тексеру үшін қатысу күйі "
                "SUBMITTED болуы қажет."
            )

        if answer_status != AssessmentAnswerStatus.PENDING_REVIEW:
            raise ValueError(
                "Қолмен тексеруге тек PENDING_REVIEW "
                "күйіндегі жауап жіберіледі."
            )

    @staticmethod
    def _validate_score(
        *,
        score: Decimal,
        max_score: Decimal,
    ) -> None:
        if max_score <= Decimal("0"):
            raise ValueError(
                "Жауаптың max_score мәні 0-ден үлкен болуы керек."
            )

        if score < Decimal("0"):
            raise ValueError(
                "Қойылған балл 0-ден төмен болмауы керек."
            )

        if score > max_score:
            raise ValueError(
                "Қойылған балл max_score мәнінен аспауы керек."
            )

    @staticmethod
    def _build_result(
        *,
        assessment: Assessment,
        participant: AssessmentStudent,
        assessment_student_answer_id: int,
        score: Decimal,
        max_score: Decimal,
        has_pending_review: bool,
    ) -> AssessmentManualGradingResult:
        return AssessmentManualGradingResult(
            assessment_id=assessment.id,
            assessment_student_id=participant.id,
            assessment_student_answer_id=(
                assessment_student_answer_id
            ),
            answer_status=AssessmentAnswerStatus.CHECKED.value,
            score=score,
            max_score=max_score,
            participation_status=(
                participant.participation_status.value
            ),
            has_pending_review=has_pending_review,
            completed_at=cast(
                datetime | None,
                participant.completed_at,
            ),
        )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)
