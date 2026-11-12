# app/modules/assessment/ai/question_validation_pipeline.py
from __future__ import annotations

from app.modules.assessment.helpers.ai_question_contract import validate_generated_question

from dataclasses import dataclass

from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIGeneratedQuestionDTO,
    AIQuestionGenerationResponseDTO,
)
from app.modules.assessment.services.assessment_question_validation_service import (
    AssessmentQuestionValidationService,
)


@dataclass(slots=True, frozen=True)
class AIQuestionValidationResult:
    """
    Результат технической проверки AI generation response.
    """

    questions: tuple[AIGeneratedQuestionDTO, ...]
    warnings: tuple[str, ...]


class AIQuestionValidationPipeline:
    """
    Техническая проверка вопросов после AI Response Parser.

    Pipeline:
    - не работает с БД;
    - не вызывает AI;
    - не создаёт QuestionBankItem;
    - не управляет транзакцией;
    - использует существующий Question Contract validator.

    Если хотя бы один вопрос некорректен,
    весь generation response отклоняется.
    """

    @classmethod
    def validate(
        cls,
        response: AIQuestionGenerationResponseDTO,
    ) -> AIQuestionValidationResult:
        if not response.questions:
            raise ValueError(
                "AI generation response "
                "не содержит вопросов."
            )

        for index, question in enumerate(
            response.questions,
            start=1,
        ):
            cls._validate_question(
                question=question,
                index=index,
            )

        return AIQuestionValidationResult(
            questions=response.questions,
            warnings=response.warnings,
        )

    @staticmethod
    def _validate_question(
        *,
        question: AIGeneratedQuestionDTO,
        index: int,
    ) -> None:
        try:
            AssessmentQuestionValidationService.validate(
                question_type=question.question_type,
                content=question.content,
                answer_key=question.answer_key,
                grading_settings=question.grading_settings,
            )

            validate_generated_question(question)

        except ValueError as exc:
            raise ValueError(
                f"AI question #{index} "
                f"({question.question_type.value}) "
                f"не прошёл Question Contract validation: "
                f"{exc}"
            ) from exc
