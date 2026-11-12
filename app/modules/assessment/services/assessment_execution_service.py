# app/modules/assessment/services/assessment_execution_service.py

from __future__ import annotations
from app.modules.assessment.helpers.assessment_names import localized

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import cast, Any
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentInputMode,
    AssessmentParticipationStatus,
    AssessmentStatus, AssessmentAnswerStatus,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentGroup,
    AssessmentStudent,
)
from app.modules.assessment.repositories.assessment_question_repo import AssessmentQuestionRepo
from app.modules.assessment.repositories.assessment_repo import (
    AssessmentRepo,
)
from app.modules.assessment.repositories.assessment_student_answer_repo import AssessmentStudentAnswerRepo
from app.modules.assessment.repositories.assessment_student_repo import (
    AssessmentStudentRepo,
)
from app.modules.assessment.schemas.assessment_execution_schemas import OnlineAssessmentPageDTO, \
    OnlineAssessmentQuestionDTO, OnlineAssessmentAnswerSaveDTO, OnlineAssessmentSubmitDTO
from app.modules.assessment.services.assessment_grading_service import (
    AssessmentGradingService,
)


@dataclass(frozen=True, slots=True)
class OnlineAssessmentAccess:
    """
    Проверенный контекст online-доступа ученика.

    raw access token здесь не хранится.
    """

    assessment: Assessment
    assessment_group: AssessmentGroup
    assessment_student: AssessmentStudent

    @property
    def assessment_id(self) -> int:
        return self.assessment.id

    @property
    def assessment_student_id(self) -> int:
        return self.assessment_student.id

    @property
    def school_id(self) -> int:
        return self.assessment.school_id


@dataclass(frozen=True, slots=True)
class IssuedAssessmentAccess:
    """
    Результат выпуска персонального access token.

    token возвращается только вызывающему коду.
    В БД сохраняется исключительно token_hash.
    """

    assessment_student_id: int
    token: str


class AssessmentExecutionService:
    """
    Бизнес-логика выполнения ONLINE Assessment.

    Ответственность:

        - генерация безопасного access token;
        - хэширование token;
        - выдача доступа участнику;
        - проверка online-доступа;
        - начало выполнения Assessment;
        - контроль duration_minutes.

    Repository Layer:
        только SQL / ORM.

    Service Layer:
        бизнес-валидация и commit / rollback.
    """

    TOKEN_BYTES = 32

    # =========================================================
    # TOKEN
    # =========================================================

    @classmethod
    def generate_access_token(cls) -> str:
        """
        Создать криптографически случайный bearer token.

        32 random bytes дают 256 бит энтропии.
        """

        return secrets.token_urlsafe(
            cls.TOKEN_BYTES
        )

    @staticmethod
    def hash_access_token(
        token: str,
    ) -> str:
        """
        Получить SHA-256 hash access token.

        В БД raw token не сохраняется.
        """

        normalized = token.strip()

        if not normalized:
            raise ValueError(
                "Access token не может быть пустым."
            )

        return hashlib.sha256(
            normalized.encode("utf-8")
        ).hexdigest()

    # =========================================================
    # ISSUE ACCESS
    # =========================================================

    @classmethod
    async def issue_student_access(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        assessment_id: int,
        assessment_student_id: int,
    ) -> IssuedAssessmentAccess:
        """
        Выпустить персональный online access token
        для одного участника Assessment.

        Разрешено только для ONLINE Assessment
        в состоянии READY или ACTIVE.

        Повторный вызов перевыпускает token:
        предыдущий token немедленно становится недействительным.
        """

        cls._validate_positive_id(
            school_id,
            field_name="school_id",
        )
        cls._validate_positive_id(
            assessment_id,
            field_name="assessment_id",
        )
        cls._validate_positive_id(
            assessment_student_id,
            field_name="assessment_student_id",
        )

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

        cls._validate_access_issue_state(
            assessment
        )

        participant = (
            await AssessmentStudentRepo
            .get_for_assessment(
                db,
                assessment_student_id=(
                    assessment_student_id
                ),
                assessment_id=assessment_id,
                school_id=school_id,
            )
        )

        if participant is None:
            raise ValueError(
                "Участник Assessment не найден."
            )

        cls._validate_participant_for_access_issue(
            participant
        )

        token = cls.generate_access_token()
        token_hash = cls.hash_access_token(
            token
        )

        try:
            await AssessmentStudentRepo.set_access_token_hash(
                db,
                assessment_student=participant,
                access_token_hash=token_hash,
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

        return IssuedAssessmentAccess(
            assessment_student_id=participant.id,
            token=token,
        )

    # =========================================================
    # RESOLVE ACCESS
    # =========================================================

    @classmethod
    async def resolve_online_access(
        cls,
        db: AsyncSession,
        *,
        token: str,
    ) -> OnlineAssessmentAccess:
        """
        Проверить bearer token и получить
        контекст online Assessment.

        Метод ничего не изменяет в БД.
        """

        token_hash = cls.hash_access_token(
            token
        )

        context = (
            await AssessmentStudentRepo
            .get_online_access_context(
                db,
                access_token_hash=token_hash,
            )
        )

        if context is None:
            raise ValueError(
                "Online Assessment с таким "
                "токеном не найден."
            )

        (
            participant,
            group,
            assessment,
        ) = context

        cls._validate_online_assessment(
            assessment
        )

        cls._validate_participant_access_state(
            participant
        )

        cls._validate_schedule(
            assessment
        )

        cls._validate_duration(
            assessment=assessment,
            participant=participant,
        )

        return OnlineAssessmentAccess(
            assessment=assessment,
            assessment_group=group,
            assessment_student=participant,
        )

    # =========================================================
    # START
    # =========================================================

    @classmethod
    async def start_assessment(
        cls,
        db: AsyncSession,
        *,
        token: str,
    ) -> OnlineAssessmentAccess:
        """
        Начать online Assessment.

        Первый вход:

            ASSIGNED
                ↓
            IN_PROGRESS

        Повторный вход при IN_PROGRESS разрешён
        и не меняет первоначальный started_at.
        """

        access = await cls.resolve_online_access(
            db,
            token=token,
        )

        participant = (
            access.assessment_student
        )

        if (
            participant.participation_status
            == AssessmentParticipationStatus.IN_PROGRESS
        ):
            return access

        if (
            participant.participation_status
            != AssessmentParticipationStatus.ASSIGNED
        ):
            raise ValueError(
                "Assessment нельзя начать "
                "в текущем состоянии участника."
            )

        now = cls._utc_now()

        try:
            participant.participation_status = (
                AssessmentParticipationStatus.IN_PROGRESS
            )

            participant.started_at = now

            await db.flush()
            await db.commit()

        except Exception:
            await db.rollback()
            raise

        return access

    # =========================================================
    # TIME
    # =========================================================

    @classmethod
    def get_remaining_seconds(
            cls,
            *,
            assessment: Assessment,
            participant: AssessmentStudent,
            now: datetime | None = None,
    ) -> int | None:
        """
        Остаток времени выполнения.

        None означает, что duration_minutes
        для Assessment не задан.
        """

        if assessment.duration_minutes is None:
            return None

        duration_minutes = cast(
            int,
            assessment.duration_minutes,
        )

        if duration_minutes <= 0:
            raise ValueError(
                "Некорректная продолжительность Assessment."
            )

        if participant.started_at is None:
            return duration_minutes * 60

        started_at = cast(
            datetime,
            participant.started_at,
        )

        current_time = (
            now
            if now is not None
            else cls._utc_now()
        )

        deadline = started_at + timedelta(minutes=duration_minutes)

        remaining = int((deadline - current_time).total_seconds())

        return max(
            remaining,
            0,
        )

    # =========================================================
    # EXECUTION PAGE
    # =========================================================

    @classmethod
    async def get_execution_page(
            cls,
            db: AsyncSession,
            *,
            token: str,
    ) -> OnlineAssessmentPageDTO:
        """
        Получить данные страницы online-выполнения.

        SQL:
            1. resolve online access;
            2. active Assessment questions;
            3. saved student answers.

        Количество запросов не зависит
        от количества вопросов.

        answer_key и grading_settings
        в student execution flow не загружаются.
        """

        # =====================================================
        # ACCESS
        # =====================================================

        access = await cls.resolve_online_access(
            db,
            token=token,
        )

        assessment = access.assessment
        group = access.assessment_group
        participant = access.assessment_student

        # =====================================================
        # QUESTIONS
        # =====================================================

        question_rows = (
            await AssessmentQuestionRepo.get_online_rows(
                db,
                assessment_id=assessment.id,
                school_id=assessment.school_id,
            )
        )

        # =====================================================
        # SAVED ANSWERS
        # =====================================================

        saved_answers = (
            await AssessmentStudentAnswerRepo
            .get_many_for_student(
                db,
                assessment_student_id=participant.id,
            )
        )

        answer_by_question_id = {
            answer.question_id: answer
            for answer in saved_answers
        }

        # =====================================================
        # DTO QUESTIONS
        # =====================================================

        question_items: list[
            OnlineAssessmentQuestionDTO
        ] = []

        for row in question_rows:
            saved_answer = (
                answer_by_question_id.get(
                    row.question_id
                )
            )

            if saved_answer is None:
                answer_data: dict[str, Any] = {}

                answer_status = (
                    AssessmentAnswerStatus.NOT_ANSWERED
                )

            else:
                answer_data = cast(
                    dict[str, Any],
                    saved_answer.answer_data,
                )

                answer_status = cast(
                    AssessmentAnswerStatus,
                    saved_answer.status,
                )

            question_items.append(
                OnlineAssessmentQuestionDTO(
                    question_id=row.question_id,
                    question_type=row.question_type,

                    text=row.text,
                    instruction=row.instruction,

                    max_score=row.max_score,
                    order_no=row.order_no,

                    content=row.content,

                    is_required=row.is_required,

                    answer_data=answer_data,
                    answer_status=answer_status,
                )
            )

        questions = tuple(
            question_items
        )

        # =====================================================
        # TIMER
        # =====================================================

        remaining_seconds = (
            cls.get_remaining_seconds(
                assessment=assessment,
                participant=participant,
            )
        )

        duration_minutes = cast(
            int | None,
            assessment.duration_minutes,
        )

        # =====================================================
        # PAGE DTO
        # =====================================================

        return OnlineAssessmentPageDTO(
            assessment_id=assessment.id,
            assessment_student_id=participant.id,

            title=localized(assessment),
            description=assessment.description,

            subject_name=(
                assessment.subject_name_snapshot
            ),

            student_name=(
                participant.student_name_snapshot
            ),

            class_name=(
                group.class_name_snapshot
            ),

            duration_minutes=duration_minutes,
            remaining_seconds=remaining_seconds,

            question_count=len(
                questions
            ),

            questions=questions,
        )
    # =========================================================
    # ANSWER AUTOSAVE
    # =========================================================

    @classmethod
    async def save_answer(
        cls,
        db: AsyncSession,
        *,
        token: str,
        question_id: int,
        answer_data: dict[str, object],
    ) -> OnlineAssessmentAnswerSaveDTO:
        """
        Autosave ответа ученика.

        Security flow:

            token
                ↓
            ONLINE + ACTIVE Assessment
                ↓
            participant == IN_PROGRESS
                ↓
            question принадлежит тому же Assessment
                ↓
            question активен
                ↓
            duration не истёк
                ↓
            upsert answer
                ↓
            commit

        Автоматическое оценивание здесь
        намеренно НЕ выполняется.
        """

        cls._validate_positive_id(
            question_id,
            field_name="question_id",
        )

        if not isinstance(
            answer_data,
            dict,
        ):
            raise ValueError(
                "Некорректный формат ответа."
            )

        # =====================================================
        # ONLINE ACCESS
        # =====================================================

        access = await cls.resolve_online_access(
            db,
            token=token,
        )

        assessment = access.assessment
        participant = access.assessment_student

        # =====================================================
        # PARTICIPANT STATE
        # =====================================================

        if (
            participant.participation_status
            != AssessmentParticipationStatus.IN_PROGRESS
        ):
            raise ValueError(
                "Сначала необходимо начать Assessment."
            )

        # =====================================================
        # QUESTION BOUNDARY
        # =====================================================

        question = (
            await AssessmentQuestionRepo.get_for_assessment(
                db,
                question_id=question_id,
                assessment_id=assessment.id,
                school_id=assessment.school_id,
            )
        )

        if question is None:
            raise ValueError(
                "Задание не найдено."
            )

        if not question.is_active:
            raise ValueError(
                "Задание недоступно."
            )

        # =====================================================
        # ANSWER STATUS
        # =====================================================

        answer_status = (
            AssessmentAnswerStatus.PENDING_REVIEW
            if answer_data
            else AssessmentAnswerStatus.NOT_ANSWERED
        )

        question_max_score = cast(
            Decimal,
            question.max_score,
        )

        # =====================================================
        # SAVE
        # =====================================================

        try:
            answer = (
                await AssessmentStudentAnswerRepo.upsert(
                    db,
                    assessment_student_id=participant.id,
                    question_id=question.id,
                    answer_data=answer_data,
                    max_score=question_max_score,
                    status=answer_status,
                    score=None,
                    is_correct=None,
                )
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

        return OnlineAssessmentAnswerSaveDTO(
            answer_id=answer.id,
            question_id=question.id,
            assessment_student_id=participant.id,
            status=answer.status.value,
        )

    # =========================================================
    # SUBMIT
    # =========================================================

    @classmethod
    async def submit_assessment(
        cls,
        db: AsyncSession,
        *,
        token: str,
    ) -> OnlineAssessmentSubmitDTO:
        """
        Финальная отправка online Assessment учеником.

        Flow:

            token
                ↓
            ONLINE + ACTIVE Assessment
                ↓
            IN_PROGRESS participant
                ↓
            active questions
                ↓
            saved answers
                ↓
            required questions validation
                ↓
            participant -> SUBMITTED
                ↓
            completed_at
                ↓
            automatic grading
                ↓
            AssessmentResult
                ↓
            one commit

        Отправка, автоматическая проверка, финализация участника
        и AssessmentResult выполняются одной транзакцией.
        """

        # =====================================================
        # ACCESS
        # =====================================================

        access = await cls.resolve_online_access(
            db,
            token=token,
        )

        assessment = access.assessment
        participant = access.assessment_student

        # =====================================================
        # PARTICIPANT STATE
        # =====================================================

        if (
            participant.participation_status
            != AssessmentParticipationStatus.IN_PROGRESS
        ):
            raise ValueError(
                "Assessment жіберу үшін алдымен "
                "оны орындауды бастау қажет."
            )

        # =====================================================
        # QUESTIONS
        # =====================================================

        question_rows = (
            await AssessmentQuestionRepo.get_online_rows(
                db,
                assessment_id=assessment.id,
                school_id=assessment.school_id,
            )
        )

        if not question_rows:
            raise ValueError(
                "Assessment тапсырмалары табылмады."
            )

        # =====================================================
        # ANSWERS
        # =====================================================

        saved_answers = (
            await AssessmentStudentAnswerRepo
            .get_many_for_student(
                db,
                assessment_student_id=participant.id,
            )
        )

        answer_by_question_id = {
            answer.question_id: answer
            for answer in saved_answers
        }

        # =====================================================
        # REQUIRED QUESTIONS
        # =====================================================

        unanswered_required_numbers: list[int] = []

        for question in question_rows:
            if not question.is_required:
                continue

            answer = answer_by_question_id.get(
                question.question_id
            )

            if answer is None:
                unanswered_required_numbers.append(
                    question.order_no
                )
                continue

            answer_data = cast(
                dict[str, Any],
                answer.answer_data,
            )

            answer_status = cast(
                AssessmentAnswerStatus,
                answer.status,
            )

            if (
                not answer_data
                or answer_status
                == AssessmentAnswerStatus.NOT_ANSWERED
            ):
                unanswered_required_numbers.append(
                    question.order_no
                )

        if unanswered_required_numbers:
            question_numbers = ", ".join(
                str(number)
                for number
                in unanswered_required_numbers
            )

            raise ValueError(
                "Міндетті тапсырмаларға жауап берілмеген: "
                f"{question_numbers}."
            )

        # =====================================================
        # SUBMIT + GRADING + FINALIZATION
        # =====================================================

        try:
            participant.participation_status = (
                AssessmentParticipationStatus.SUBMITTED
            )
            participant.completed_at = None

            await db.flush()

            grading_result = await AssessmentGradingService.grade_student(
                db,
                assessment=assessment,
                participant=participant,
            )

            if grading_result.has_pending_review:
                participant.participation_status = (
                    AssessmentParticipationStatus.SUBMITTED
                )
                participant.completed_at = None
            else:
                participant.participation_status = (
                    AssessmentParticipationStatus.COMPLETED
                )
                participant.completed_at = cls._utc_now()

            await db.flush()
            await db.commit()

        except Exception:
            await db.rollback()
            raise

        completed_at = cast(
            datetime | None,
            participant.completed_at,
        )

        return OnlineAssessmentSubmitDTO(
            assessment_id=assessment.id,
            assessment_student_id=participant.id,
            participation_status=(
                participant.participation_status.value
            ),
            completed_at=(
                completed_at.isoformat()
                if completed_at is not None
                else None
            ),
        )

    # =========================================================
    # VALIDATION
    # =========================================================

    @staticmethod
    def _validate_access_issue_state(
        assessment: Assessment,
    ) -> None:
        if (
            assessment.input_mode
            != AssessmentInputMode.ONLINE
        ):
            raise ValueError(
                "Access token можно выдавать только "
                "для ONLINE Assessment."
            )

        if assessment.status not in {
            AssessmentStatus.READY,
            AssessmentStatus.ACTIVE,
        }:
            raise ValueError(
                "Access token можно выдавать только "
                "для подготовленного или активного Assessment."
            )

        if (
            assessment.max_score is None
            or assessment.max_score <= 0
        ):
            raise ValueError(
                "ONLINE Assessment должен иметь "
                "положительный максимальный балл."
            )

    @staticmethod
    def _validate_participant_for_access_issue(
        participant: AssessmentStudent,
    ) -> None:
        if participant.participation_status not in {
            AssessmentParticipationStatus.ASSIGNED,
            AssessmentParticipationStatus.IN_PROGRESS,
        }:
            raise ValueError(
                "Нельзя выдать online-доступ участнику "
                "в текущем состоянии."
            )

    @staticmethod
    def _validate_online_assessment(
        assessment: Assessment,
    ) -> None:
        if (
            assessment.input_mode
            != AssessmentInputMode.ONLINE
        ):
            raise ValueError(
                "Assessment не предназначен "
                "для online-выполнения."
            )

        if (
            assessment.status
            != AssessmentStatus.ACTIVE
        ):
            raise ValueError(
                "Assessment сейчас не активен."
            )

        if (
            assessment.max_score is None
            or assessment.max_score <= 0
        ):
            raise ValueError(
                "У Assessment не задан "
                "корректный максимальный балл."
            )

    @staticmethod
    def _validate_participant_access_state(
        participant: AssessmentStudent,
    ) -> None:
        if participant.participation_status in {
            AssessmentParticipationStatus.ASSIGNED,
            AssessmentParticipationStatus.IN_PROGRESS,
        }:
            return

        if (
            participant.participation_status
            == AssessmentParticipationStatus.SUBMITTED
        ):
            raise ValueError(
                "Assessment тексеруге жіберілген."
            )

        if (
            participant.participation_status
            == AssessmentParticipationStatus.COMPLETED
        ):
            raise ValueError(
                "Assessment уже выполнен."
            )

        raise ValueError(
            "Участнику недоступно выполнение Assessment."
        )

    @classmethod
    def _validate_schedule(
        cls,
        assessment: Assessment,
    ) -> None:
        """
        scheduled_at трактуем как время,
        раньше которого Assessment начинать нельзя.

        Отдельного deadline поля в текущей модели нет.
        """

        if assessment.scheduled_at is None:
            return

        if cls._utc_now() < assessment.scheduled_at:
            raise ValueError(
                "Время начала Assessment ещё не наступило."
            )

    @classmethod
    def _validate_duration(
        cls,
        *,
        assessment: Assessment,
        participant: AssessmentStudent,
    ) -> None:
        """
        Проверить персональный лимит времени.

        Таймер начинается от
        AssessmentStudent.started_at.

        Здесь статус автоматически не меняется:
        финальное решение о NOT_COMPLETED
        будет частью submit/finalization flow.
        """

        if participant.started_at is None:
            return

        remaining = cls.get_remaining_seconds(
            assessment=assessment,
            participant=participant,
        )

        if remaining is None:
            return

        if remaining <= 0:
            raise ValueError(
                "Время выполнения Assessment истекло."
            )

    # =========================================================
    # HELPERS
    # =========================================================

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(
            timezone.utc
        )

    @staticmethod
    def _validate_positive_id(
        value: int,
        *,
        field_name: str,
    ) -> None:
        if value <= 0:
            raise ValueError(
                f"Некорректный {field_name}."
            )
