# app/modules/assessment/services/assessment_grading_service.py

from __future__ import annotations

from app.modules.assessment.helpers.true_false_score_policy import grade_true_false
from app.modules.assessment.helpers.number_score_policy import grade_number_parts
from app.modules.assessment.helpers.matching_score_policy import grade_matching_pairs
from app.modules.assessment.helpers.ordering_score_policy import grade_ordering_positions
from app.modules.assessment.helpers.fill_gaps_score_policy import grade_fill_gaps

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentAnswerStatus,
    AssessmentParticipationStatus,
    AssessmentQuestionType,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentQuestion,
    AssessmentResult,
    AssessmentStudent,
    AssessmentStudentAnswer,
)
from app.modules.assessment.repositories.assessment_question_repo import (
    AssessmentQuestionRepo,
)
from app.modules.assessment.repositories.assessment_result_repo import (
    AssessmentResultRepo,
)
from app.modules.assessment.repositories.assessment_student_answer_repo import (
    AssessmentStudentAnswerRepo,
)
from app.modules.assessment.services.assessment_scoring_service import (
    AssessmentScoringService,
)


# =========================================================
# DTO
# =========================================================


@dataclass(frozen=True, slots=True)
class AssessmentGradingResult:
    """
    Результат проверки одного участника.

    Если has_pending_review == True:
        - работа остаётся SUBMITTED;
        - AssessmentResult ещё не создаётся;
        - score / percent / grade_value являются None.

    Если has_pending_review == False:
        - все ответы проверены;
        - рассчитан финальный AssessmentResult.
    """

    assessment_id: int
    assessment_student_id: int

    score: Decimal | None
    max_score: Decimal
    percent: Decimal | None

    grade_value: str | None

    checked_answers_count: int
    pending_answers_count: int
    has_pending_review: bool


# =========================================================
# SERVICE
# =========================================================


class AssessmentGradingService:
    """
    Автоматическая проверка online Assessment.

    Ответственность:

        AssessmentQuestion.answer_key
            +
        AssessmentStudentAnswer.answer_data
            ↓
        score / is_correct / CHECKED
            ↓
        AssessmentScoringService
            ↓
        AssessmentResultRepo
            ↓
        AssessmentResult

    В этом сервисе нет:

        - student token validation;
        - online execution;
        - final participant status transition;
        - AssessmentQualitySummary;
        - teacher result UI.

    Поддерживаемые типы автоматической проверки:

        SINGLE_CHOICE
        MULTIPLE_CHOICE
        TRUE_FALSE

    Остальные типы добавляются только после определения
    их стабильного answer_data / answer_key контракта.
    """

    # =====================================================
    # PUBLIC
    # =====================================================

    @classmethod
    async def grade_student(
            cls,
            db: AsyncSession,
            *,
            assessment: Assessment,
            participant: AssessmentStudent,
    ) -> AssessmentGradingResult:
        """
        Автоматически проверить ответы одного участника
        и создать / обновить AssessmentResult.

        Участник должен передать работу на проверку:

            participation_status == SUBMITTED

        Метод:

            - загружает все активные вопросы одним запросом;
            - загружает все существующие ответы одним запросом;
            - создаёт отсутствующие AssessmentStudentAnswer batch-операцией;
            - автоматически проверяет поддерживаемые типы;
            - оставляет неподдерживаемые ответы PENDING_REVIEW;
            - создаёт AssessmentResult только если ручная
              проверка больше не требуется.

        После синхронизации действует инвариант:

            каждый активный AssessmentQuestion
            имеет AssessmentStudentAnswer
            для данного участника.

        Метод НЕ выполняет commit / rollback.
        Границу транзакции определяет вызывающий сервис.
        """

        cls._validate_context(
            assessment=assessment,
            participant=participant,
        )

        # =================================================
        # QUESTIONS
        # =================================================

        questions = (
            await AssessmentQuestionRepo.get_many_for_assessment(
                db,
                assessment_id=assessment.id,
                school_id=assessment.school_id,
                include_inactive=False,
            )
        )

        if not questions:
            raise ValueError(
                "Assessment тапсырмалары табылмады."
            )

        # =================================================
        # EXISTING ANSWERS
        # =================================================

        answers = (
            await AssessmentStudentAnswerRepo.get_many_for_student(
                db,
                assessment_student_id=participant.id,
            )
        )

        answer_by_question_id = {
            answer.question_id: answer
            for answer in answers
        }

        # =================================================
        # ENSURE ANSWER ROW FOR EVERY ACTIVE QUESTION
        # =================================================

        missing_answers = (
            await AssessmentStudentAnswerRepo.add_missing_for_questions(
                db,
                assessment_student_id=participant.id,
                questions=questions,
                existing_question_ids=set(
                    answer_by_question_id.keys()
                ),
            )
        )

        if missing_answers:
            answers.extend(missing_answers)

            for answer in missing_answers:
                answer_by_question_id[answer.question_id] = answer

        # =================================================
        # GRADE ANSWERS
        # =================================================

        total_max_score = Decimal("0")
        checked_answers_count = 0

        checked_at = cls._utc_now()

        for question in questions:
            question_max_score = cast(
                Decimal,
                question.max_score,
            )

            total_max_score += question_max_score

            answer = answer_by_question_id.get(
                question.id
            )

            # После add_missing_for_questions() отсутствие
            # answer является нарушением внутреннего инварианта.
            if answer is None:
                raise ValueError(
                    "AssessmentStudentAnswer missing after "
                    "answer-row synchronization: "
                    f"assessment_student_id={participant.id}, "
                    f"question_id={question.id}."
                )

            answer_data = cast(
                dict[str, Any],
                answer.answer_data,
            )

            # -----------------------------------------
            # NOT ANSWERED
            # -----------------------------------------

            if not answer_data:
                cls._mark_not_answered(
                    answer=answer,
                    max_score=question_max_score,
                )
                continue

            # -----------------------------------------
            # SINGLE CHOICE
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.SINGLE_CHOICE
            ):
                cls._grade_single_choice(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # MULTIPLE CHOICE
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.MULTIPLE_CHOICE
            ):
                cls._grade_multiple_choice(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # TRUE / FALSE
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.TRUE_FALSE
            ):
                cls._grade_true_false(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # SHORT TEXT
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.SHORT_TEXT
            ):
                cls._grade_short_text(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # NUMBER
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.NUMBER
            ):
                cls._grade_number(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # MATCHING
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.MATCHING
            ):
                cls._grade_matching(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # ORDERING
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.ORDERING
            ):
                cls._grade_ordering(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # FILL GAPS
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.FILL_GAPS
            ):
                cls._grade_fill_gaps(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # IMAGE CHOICE
            # -----------------------------------------

            if (
                    question.question_type
                    == AssessmentQuestionType.IMAGE_CHOICE
            ):
                cls._grade_image_choice(
                    question=question,
                    answer=answer,
                    checked_at=checked_at,
                )

                checked_answers_count += 1
                continue

            # -----------------------------------------
            # NOT YET AUTO-GRADED
            #
            # FORMULA
            # MANUAL_REVIEW
            # -----------------------------------------

            cls._mark_pending_review(
                answer=answer,
                max_score=question_max_score,
            )

        # =================================================
        # PENDING MANUAL REVIEW
        # =================================================

        pending_answers = [
            answer
            for answer in answers
            if (
                    answer.status
                    == AssessmentAnswerStatus.PENDING_REVIEW
            )
        ]

        pending_answers_count = len(
            pending_answers
        )

        if pending_answers_count:
            await db.flush()

            return cls._build_pending_result(
                assessment=assessment,
                participant=participant,
                max_score=total_max_score,
                checked_answers_count=checked_answers_count,
                pending_answers_count=pending_answers_count,
            )

        # =================================================
        # FINAL RESULT
        # =================================================

        assessment_result = (
            await cls.finalize_student_result(
                db,
                assessment=assessment,
                participant=participant,
                calculated_at=checked_at,
            )
        )

        return cls._build_final_result(
            assessment=assessment,
            participant=participant,
            assessment_result=assessment_result,
            checked_answers_count=checked_answers_count,
        )
    
    @classmethod
    async def finalize_student_result(
            cls,
            db: AsyncSession,
            *,
            assessment: Assessment,
            participant: AssessmentStudent,
            calculated_at: datetime | None = None,
    ) -> AssessmentResult:
        """
        Финализировать итоговый AssessmentResult участника
        по уже проверенным ответам.

        Используется:
            - после полной автоматической проверки;
            - после проверки последнего ручного ответа.

        Условия:
            - participant должен находиться в SUBMITTED;
            - PENDING_REVIEW ответов быть не должно;
            - все сохранённые ответы должны быть CHECKED.

        Метод:
            - повторно загружает ответы из БД;
            - суммирует score / max_score;
            - рассчитывает percent / grade;
            - создаёт или обновляет AssessmentResult;
            - выполняет flush.

        Метод НЕ выполняет commit / rollback.
        Транзакцией владеет вызывающий Service Layer.
        """

        cls._validate_context(
            assessment=assessment,
            participant=participant,
        )

        answers = (
            await AssessmentStudentAnswerRepo
            .get_many_for_student(
                db,
                assessment_student_id=participant.id,
            )
        )

        if not answers:
            raise ValueError(
                "Assessment қатысушысының жауаптары табылмады."
            )

        pending_answers = [
            answer
            for answer in answers
            if (
                    answer.status
                    == AssessmentAnswerStatus.PENDING_REVIEW
            )
        ]

        if pending_answers:
            raise ValueError(
                "Assessment нәтижесін аяқтау мүмкін емес: "
                "қолмен тексеруді күтетін жауаптар бар."
            )

        unchecked_answers = [
            answer
            for answer in answers
            if (
                    answer.status
                    != AssessmentAnswerStatus.CHECKED
            )
        ]

        if unchecked_answers:
            raise ValueError(
                "Assessment нәтижесін аяқтау мүмкін емес: "
                "тексерілмеген жауаптар бар."
            )

        total_score = Decimal("0")
        total_max_score = Decimal("0")

        for answer in answers:
            answer_score = cast(
                Decimal | None,
                answer.score,
            )

            answer_max_score = cast(
                Decimal | None,
                answer.max_score,
            )

            if answer_score is None:
                raise ValueError(
                    "CHECKED жауабында score жоқ: "
                    f"answer_id={answer.id}."
                )

            if answer_max_score is None:
                raise ValueError(
                    "CHECKED жауабында max_score жоқ: "
                    f"answer_id={answer.id}."
                )

            if answer_score < Decimal("0"):
                raise ValueError(
                    "Жауап балы 0-ден төмен болмауы керек: "
                    f"answer_id={answer.id}."
                )

            if answer_score > answer_max_score:
                raise ValueError(
                    "Жауап балы max_score мәнінен аспауы керек: "
                    f"answer_id={answer.id}."
                )

            total_score += answer_score
            total_max_score += answer_max_score

        scoring = AssessmentScoringService.calculate(
            score=total_score,
            max_score=total_max_score,
        )

        result_calculated_at = (
            calculated_at
            if calculated_at is not None
            else cls._utc_now()
        )

        assessment_result = (
            await AssessmentResultRepo.upsert(
                db,
                assessment_student_id=participant.id,
                score=scoring.score,
                max_score=scoring.max_score,
                percent=scoring.percent,
                grade=scoring.grade,
                calculated_at=result_calculated_at,
            )
        )

        await db.flush()

        return assessment_result

    # =====================================================
    # SINGLE CHOICE
    # =====================================================

    @classmethod
    def _grade_single_choice(
            cls,
            *,
            question: AssessmentQuestion,
            answer: AssessmentStudentAnswer,
            checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_single_choice(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        """
        Контракт:

            answer_key:
                {
                    "value": "B"
                }

            answer_data:
                {
                    "value": "B"
                }

        Полное совпадение:
            max_score

        Ошибка:
            0
        """

        if 'parts' in question.content or 'single_choice_score_policy' in question.grading_settings:
            from app.modules.assessment.helpers.single_choice_score_policy import grade_single_choice_parts
            score, correct = grade_single_choice_parts(content=question.content, answer_key=question.answer_key,
                grading_settings=question.grading_settings, answer_data=answer.answer_data or {}, max_score=question.max_score)
            answer.score = score
            answer.max_score = question.max_score
            answer.is_correct = correct
            answer.status = AssessmentAnswerStatus.CHECKED
            answer.checked_by_user_id = None
            answer.checked_at = checked_at
            return

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        correct_value = answer_key["value"]

        student_value = answer_data.get(
            "value"
        )

        is_correct = (
                student_value == correct_value
        )

        max_score = cast(
            Decimal,
            question.max_score,
        )

        score = (
            max_score
            if is_correct
            else Decimal("0")
        )

        answer.score = score
        answer.max_score = max_score
        answer.is_correct = is_correct
        answer.status = AssessmentAnswerStatus.CHECKED

        # Автоматическая проверка выполняется системой,
        # поэтому user checker отсутствует.
        answer.checked_by_user_id = None
        answer.checked_at = checked_at

    # =====================================================
    # MULTIPLE CHOICE
    # =====================================================

    @classmethod
    def _grade_multiple_choice(
            cls,
            *,
            question: AssessmentQuestion,
            answer: AssessmentStudentAnswer,
            checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_multiple_choice(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        """
        Контракт:

            answer_key:
                {
                    "values": ["A", "C"]
                }

            answer_data:
                {
                    "values": ["A", "C"]
                }

        Порядок выбранных значений не влияет на результат.
        Для полного совпадения начисляется max_score,
        иначе 0 баллов.
        """

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        correct_values = set(answer_key["values"])

        raw_student_values = answer_data.get(
            "values",
            [],
        )

        student_values = (
            set(raw_student_values)
            if isinstance(raw_student_values, list)
            else set()
        )

        is_correct = student_values == correct_values

        max_score = cast(
            Decimal,
            question.max_score,
        )

        score = (
            max_score
            if is_correct
            else Decimal("0")
        )

        answer.score = score
        answer.max_score = max_score
        answer.is_correct = is_correct
        answer.status = AssessmentAnswerStatus.CHECKED
        answer.checked_by_user_id = None
        answer.checked_at = checked_at

    # =====================================================
    # TRUE / FALSE
    # =====================================================

    @classmethod
    def _grade_true_false(
            cls,
            *,
            question: AssessmentQuestion,
            answer: AssessmentStudentAnswer,
            checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_true_false(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        """Legacy value: all-or-nothing; statements: one point per correct boolean.
        Missing values earn zero. Only a fully correct submission sets is_correct.
        """

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        max_score = cast(Decimal, question.max_score)
        score, is_correct = grade_true_false(
            content=cast(dict[str, Any], question.content), answer_key=answer_key,
            answer_data=answer_data, max_score=max_score,
        )

        answer.score = score
        answer.max_score = max_score
        answer.is_correct = is_correct
        answer.status = AssessmentAnswerStatus.CHECKED
        answer.checked_by_user_id = None
        answer.checked_at = checked_at

    # =====================================================
    # SHORT TEXT
    # =====================================================

    @classmethod
    def _grade_short_text(
        cls,
        *,
        question: AssessmentQuestion,
        answer: AssessmentStudentAnswer,
        checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_short_text(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        grading_settings = cast(
            dict[str, Any],
            question.grading_settings,
        )

        accepted_answers = answer_key.get(
            "accepted_answers",
            [],
        )

        student_text = answer_data.get("text")

        case_sensitive = grading_settings.get(
            "case_sensitive",
            False,
        )

        trim_whitespace = grading_settings.get(
            "trim_whitespace",
            True,
        )

        is_correct = False

        if isinstance(student_text, str):
            normalized_student = cls._normalize_text(
                student_text,
                case_sensitive=case_sensitive,
                trim_whitespace=trim_whitespace,
            )

            normalized_answers = {
                cls._normalize_text(
                    value,
                    case_sensitive=case_sensitive,
                    trim_whitespace=trim_whitespace,
                )
                for value in accepted_answers
                if isinstance(value, str)
            }

            is_correct = (
                normalized_student
                in normalized_answers
            )

        cls._apply_auto_grade(
            question=question,
            answer=answer,
            is_correct=is_correct,
            checked_at=checked_at,
        )

    # =====================================================
    # NUMBER
    # =====================================================

    @classmethod
    def _grade_number(
        cls,
        *,
        question: AssessmentQuestion,
        answer: AssessmentStudentAnswer,
        checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_number(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        if "parts" in question.content:
            score, is_correct = grade_number_parts(
                content=question.content, answer_key=question.answer_key,
                grading_settings=question.grading_settings, answer_data=answer.answer_data,
                max_score=question.max_score,
            )
            answer.score = score
            answer.max_score = question.max_score
            answer.is_correct = is_correct
            answer.status = AssessmentAnswerStatus.CHECKED
            answer.checked_by_user_id = None
            answer.checked_at = checked_at
            return

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        grading_settings = cast(
            dict[str, Any],
            question.grading_settings,
        )

        correct_value = answer_key.get("value")
        student_value = answer_data.get("value")

        tolerance = grading_settings.get(
            "tolerance",
            0,
        )

        is_correct = False

        if (
            cls._is_number(correct_value)
            and cls._is_number(student_value)
            and cls._is_number(tolerance)
        ):
            correct_decimal = Decimal(
                str(correct_value)
            )

            student_decimal = Decimal(
                str(student_value)
            )

            tolerance_decimal = Decimal(
                str(tolerance)
            )

            is_correct = (
                abs(
                    student_decimal
                    - correct_decimal
                )
                <= tolerance_decimal
            )

        cls._apply_auto_grade(
            question=question,
            answer=answer,
            is_correct=is_correct,
            checked_at=checked_at,
        )

    # =====================================================
    # MATCHING
    # =====================================================

    @classmethod
    def _grade_matching(
        cls,
        *,
        question: AssessmentQuestion,
        answer: AssessmentStudentAnswer,
        checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_matching(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        if question.grading_settings.get("matching_score_policy") == "per_pair_v1":
            score, is_correct = grade_matching_pairs(
                content=question.content, answer_key=question.answer_key,
                grading_settings=question.grading_settings, answer_data=answer.answer_data,
                max_score=question.max_score,
            )
            answer.score = score
            answer.max_score = question.max_score
            answer.is_correct = is_correct
            answer.status = AssessmentAnswerStatus.CHECKED
            answer.checked_by_user_id = None
            answer.checked_at = checked_at
            return

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        correct_pairs = cls._pairs_to_set(
            answer_key.get("pairs")
        )

        student_pairs = cls._pairs_to_set(
            answer_data.get("pairs")
        )

        is_correct = (
            correct_pairs is not None
            and student_pairs is not None
            and student_pairs == correct_pairs
        )

        cls._apply_auto_grade(
            question=question,
            answer=answer,
            is_correct=is_correct,
            checked_at=checked_at,
        )

    # =====================================================
    # ORDERING
    # =====================================================

    @classmethod
    def _grade_ordering(
        cls,
        *,
        question: AssessmentQuestion,
        answer: AssessmentStudentAnswer,
        checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_ordering(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        if question.grading_settings.get("ordering_score_policy") == "per_position_v1":
            score, is_correct = grade_ordering_positions(
                content=question.content, answer_key=question.answer_key,
                grading_settings=question.grading_settings, answer_data=answer.answer_data,
                max_score=question.max_score,
            )
            answer.score = score
            answer.max_score = question.max_score
            answer.is_correct = is_correct
            answer.status = AssessmentAnswerStatus.CHECKED
            answer.checked_by_user_id = None
            answer.checked_at = checked_at
            return

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        correct_order = answer_key.get("order")
        student_order = answer_data.get("order")

        is_correct = (
            isinstance(correct_order, list)
            and isinstance(student_order, list)
            and student_order == correct_order
        )

        cls._apply_auto_grade(
            question=question,
            answer=answer,
            is_correct=is_correct,
            checked_at=checked_at,
        )

    # =====================================================
    # FILL GAPS
    # =====================================================

    @classmethod
    def _grade_fill_gaps(
        cls,
        *,
        question: AssessmentQuestion,
        answer: AssessmentStudentAnswer,
        checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_fill_gaps(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        if question.grading_settings.get("fill_gaps_score_policy") == "per_gap_v1":
            score, is_correct = grade_fill_gaps(
                content=question.content, answer_key=question.answer_key,
                grading_settings=question.grading_settings, answer_data=answer.answer_data,
                max_score=question.max_score,
            )
            answer.score = score
            answer.max_score = question.max_score
            answer.is_correct = is_correct
            answer.status = AssessmentAnswerStatus.CHECKED
            answer.checked_by_user_id = None
            answer.checked_at = checked_at
            return

        answer_key = cast(
            dict[str, Any],
            question.answer_key,
        )

        answer_data = cast(
            dict[str, Any],
            answer.answer_data,
        )

        grading_settings = cast(
            dict[str, Any],
            question.grading_settings,
        )

        correct_gaps = answer_key.get("gaps")
        student_gaps = answer_data.get("gaps")

        case_sensitive = grading_settings.get(
            "case_sensitive",
            False,
        )

        trim_whitespace = grading_settings.get(
            "trim_whitespace",
            True,
        )

        is_correct = True

        if (
            not isinstance(correct_gaps, dict)
            or not isinstance(student_gaps, dict)
            or set(student_gaps.keys())
            != set(correct_gaps.keys())
        ):
            is_correct = False

        else:
            for gap_id, gap_key in correct_gaps.items():
                if not isinstance(gap_key, dict):
                    is_correct = False
                    break

                accepted_answers = gap_key.get(
                    "accepted_answers",
                    [],
                )

                student_value = student_gaps.get(
                    gap_id
                )

                if not isinstance(
                    student_value,
                    str,
                ):
                    is_correct = False
                    break

                normalized_student = (
                    cls._normalize_text(
                        student_value,
                        case_sensitive=(
                            case_sensitive
                        ),
                        trim_whitespace=(
                            trim_whitespace
                        ),
                    )
                )

                normalized_answers = {
                    cls._normalize_text(
                        value,
                        case_sensitive=(
                            case_sensitive
                        ),
                        trim_whitespace=(
                            trim_whitespace
                        ),
                    )
                    for value in accepted_answers
                    if isinstance(value, str)
                }

                if (
                    normalized_student
                    not in normalized_answers
                ):
                    is_correct = False
                    break

        cls._apply_auto_grade(
            question=question,
            answer=answer,
            is_correct=is_correct,
            checked_at=checked_at,
        )

    # =====================================================
    # IMAGE CHOICE
    # =====================================================

    @classmethod
    def _grade_image_choice(
        cls,
        *,
        question: AssessmentQuestion,
        answer: AssessmentStudentAnswer,
        checked_at: datetime,
    ) -> None:
        from app.modules.assessment.helpers.element_scoring import weighted, clean_grading, validate_elements
        if weighted(question.grading_settings):
            from types import SimpleNamespace
            validate_elements(question.question_type.value, question.content, question.answer_key, question.grading_settings, question.max_score)
            meta=question.grading_settings
            unit=SimpleNamespace(question_type=question.question_type,content=question.content,answer_key=question.answer_key,
                grading_settings=clean_grading(meta),max_score=Decimal(meta['element_count']))
            cls._grade_image_choice(question=unit,answer=answer,checked_at=checked_at)
            answer.score=Decimal(answer.score)*Decimal(meta['points_per_element'])
            answer.max_score=question.max_score
            return

        """
        IMAGE_CHOICE имеет ту же семантику ответа,
        что и SINGLE_CHOICE.

        Renderer отличается, grading — нет.
        """

        cls._grade_single_choice(
            question=question,
            answer=answer,
            checked_at=checked_at,
        )

    # =====================================================
    # AUTO GRADING HELPERS
    # =====================================================

    @staticmethod
    def _apply_auto_grade(
        *,
        question: AssessmentQuestion,
        answer: AssessmentStudentAnswer,
        is_correct: bool,
        checked_at: datetime,
    ) -> None:
        max_score = cast(
            Decimal,
            question.max_score,
        )

        answer.score = (
            max_score
            if is_correct
            else Decimal("0")
        )

        answer.max_score = max_score
        answer.is_correct = is_correct
        answer.status = AssessmentAnswerStatus.CHECKED
        answer.checked_by_user_id = None
        answer.checked_at = checked_at

    @staticmethod
    def _normalize_text(
        value: str,
        *,
        case_sensitive: bool,
        trim_whitespace: bool,
    ) -> str:
        normalized = value

        if trim_whitespace:
            normalized = normalized.strip()

        if not case_sensitive:
            normalized = normalized.casefold()

        return normalized

    @staticmethod
    def _is_number(
        value: Any,
    ) -> bool:
        return (
            isinstance(
                value,
                (int, float, Decimal),
            )
            and not isinstance(value, bool)
        )

    @staticmethod
    def _pairs_to_set(
        raw_pairs: Any,
    ) -> set[tuple[str, str]] | None:
        if not isinstance(raw_pairs, list):
            return None

        result: set[tuple[str, str]] = set()

        for pair in raw_pairs:
            if not isinstance(pair, dict):
                return None

            left = pair.get("left")
            right = pair.get("right")

            if (
                not isinstance(left, str)
                or not isinstance(right, str)
            ):
                return None

            result.add(
                (left, right)
            )

        return result

    # =====================================================
    # ANSWER STATE
    # =====================================================

    @staticmethod
    def _mark_not_answered(
            *,
            answer: AssessmentStudentAnswer,
            max_score: Decimal,
    ) -> None:
        """
        Пустой ответ.

        Такой ответ получает 0 баллов.
        """

        answer.score = Decimal("0")
        answer.max_score = max_score
        answer.is_correct = False
        answer.status = (
            AssessmentAnswerStatus.CHECKED
        )
        answer.checked_by_user_id = None
        answer.checked_at = None

    @staticmethod
    def _mark_pending_review(
            *,
            answer: AssessmentStudentAnswer,
            max_score: Decimal,
    ) -> None:
        """
        Тип задания пока не поддерживает
        автоматическую проверку.
        """

        answer.score = None
        answer.max_score = max_score
        answer.is_correct = None
        answer.status = (
            AssessmentAnswerStatus.PENDING_REVIEW
        )
        answer.checked_by_user_id = None
        answer.checked_at = None

    # =====================================================
    # VALIDATION
    # =====================================================

    @staticmethod
    def _validate_context(
            *,
            assessment: Assessment,
            participant: AssessmentStudent,
    ) -> None:
        if assessment.id <= 0:
            raise ValueError(
                "Некорректный assessment_id."
            )

        if participant.id <= 0:
            raise ValueError(
                "Некорректный assessment_student_id."
            )

        if (
                participant.school_id
                != assessment.school_id
        ):
            raise ValueError(
                "Assessment қатысушысы басқа мектепке тиесілі."
            )

        if (
                participant.participation_status
                != AssessmentParticipationStatus.SUBMITTED
        ):
            raise ValueError(
                "Assessment жұмысын тексеру үшін "
                "қатысу күйі SUBMITTED болуы қажет."
            )
    # =====================================================
    # RESULT DTO
    # =====================================================

    @staticmethod
    def _build_pending_result(
            *,
            assessment: Assessment,
            participant: AssessmentStudent,
            max_score: Decimal,
            checked_answers_count: int,
            pending_answers_count: int,
    ) -> AssessmentGradingResult:
        return AssessmentGradingResult(
            assessment_id=assessment.id,
            assessment_student_id=participant.id,
            score=None,
            max_score=max_score,
            percent=None,
            grade_value=None,
            checked_answers_count=checked_answers_count,
            pending_answers_count=pending_answers_count,
            has_pending_review=True,
        )

    @staticmethod
    def _build_final_result(
            *,
            assessment: Assessment,
            participant: AssessmentStudent,
            assessment_result: AssessmentResult,
            checked_answers_count: int,
    ) -> AssessmentGradingResult:
        return AssessmentGradingResult(
            assessment_id=assessment.id,
            assessment_student_id=participant.id,
            score=cast(
                Decimal,
                assessment_result.score,
            ),
            max_score=cast(
                Decimal,
                assessment_result.max_score,
            ),
            percent=cast(
                Decimal,
                assessment_result.percent,
            ),
            grade_value=assessment_result.grade.value,
            checked_answers_count=checked_answers_count,
            pending_answers_count=0,
            has_pending_review=False,
        )

    # =====================================================
    # TIME
    # =====================================================

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(
            timezone.utc
        )
