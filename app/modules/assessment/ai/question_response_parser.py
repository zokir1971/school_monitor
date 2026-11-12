# app/modules/assessment/ai/question_response_parser.py
from __future__ import annotations

from app.modules.assessment.helpers.ai_question_contract import normalize_text_segments, segments_plain_text

from app.modules.assessment.helpers.ai_formula_segments import normalize_ai_formula_segments
from app.modules.assessment.helpers.math_prose import readable_math_prose

import json
from decimal import Decimal, InvalidOperation
from typing import Any

from app.modules.assessment.enums import (
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
)
from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIGeneratedQuestionDTO,
    AIQuestionGenerationRequestDTO,
    AIQuestionGenerationResponseDTO,
)


class AIQuestionResponseParser:
    """
    Преобразует недоверенный structured response AI
    в внутренние DTO School Monitor.

    Parser проверяет:
    - JSON;
    - верхнеуровневую структуру;
    - обязательные поля;
    - enum values;
    - scalar/container types;
    - max_score;
    - learning_objective_ids;
    - количество вопросов;
    - общий max_score;
    - распределение question_type.

    Parser НЕ проверяет семантику Question Contract.
    Это задача AssessmentQuestionValidationService.
    """

    @classmethod
    def parse_json(
        cls,
        *,
        raw_json: str,
        request: AIQuestionGenerationRequestDTO,
    ) -> AIQuestionGenerationResponseDTO:
        if not isinstance(raw_json, str):
            raise ValueError(
                "AI response должен быть строкой JSON."
            )

        if not raw_json.strip():
            raise ValueError(
                "AI response не должен быть пустым."
            )

        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "AI вернул некорректный JSON."
            ) from exc

        return cls.parse_payload(
            payload=payload,
            request=request,
        )

    @classmethod
    def parse_payload(
        cls,
        *,
        payload: Any,
        request: AIQuestionGenerationRequestDTO,
    ) -> AIQuestionGenerationResponseDTO:
        if not isinstance(payload, dict):
            raise ValueError(
                "Корень AI response должен быть object."
            )

        questions_raw = payload.get("questions")

        if not isinstance(questions_raw, list):
            raise ValueError(
                "AI response.questions должен быть list."
            )

        warnings = cls._parse_warnings(
            payload.get("warnings", [])
        )

        questions = tuple(
            cls._parse_question(
                raw_question=raw_question,
                request=request,
                index=index,
            )
            for index, raw_question in enumerate(
                questions_raw,
                start=1,
            )
        )

        response = AIQuestionGenerationResponseDTO(
            questions=questions,
            warnings=warnings,
            # Provider metadata приходит не от модели.
            metadata={},
        )

        cls._validate_response_totals(
            response=response,
            request=request,
        )

        return response

    # ============================================================
    # QUESTION
    # ============================================================

    @classmethod
    def _parse_question(
        cls,
        *,
        raw_question: Any,
        request: AIQuestionGenerationRequestDTO,
        index: int,
    ) -> AIGeneratedQuestionDTO:
        prefix = f"questions[{index}]"

        if not isinstance(raw_question, dict):
            raise ValueError(
                f"{prefix} должен быть object."
            )

        question_type = cls._parse_question_type(
            raw_question.get("question_type"),
            prefix=prefix,
        )

        difficulty = cls._parse_difficulty(
            raw_question.get("difficulty"),
            prefix=prefix,
        )

        text = cls._require_non_empty_string(
            raw_question.get("text"),
            field=f"{prefix}.text",
        )

        title = cls._optional_string(
            raw_question.get("title"),
            field=f"{prefix}.title",
        )

        instruction = cls._optional_string(
            raw_question.get("instruction"),
            field=f"{prefix}.instruction",
        )

        explanation = cls._optional_string(
            raw_question.get("explanation"),
            field=f"{prefix}.explanation",
        )
        explanation = readable_math_prose(explanation)

        content = cls._require_dict(
            raw_question.get("content"),
            field=f"{prefix}.content",
        )

        answer_key = cls._require_dict(
            raw_question.get("answer_key"),
            field=f"{prefix}.answer_key",
        )

        grading_settings = cls._require_dict(
            raw_question.get("grading_settings"),
            field=f"{prefix}.grading_settings",
        )

        max_score = cls._parse_positive_decimal(
            raw_question.get("max_score"),
            field=f"{prefix}.max_score",
        )

        learning_objective_ids = (
            cls._parse_learning_objective_ids(
                raw_question.get(
                    "learning_objective_ids",
                    [],
                ),
                request=request,
                prefix=prefix,
            )
        )

        if "text_segments" in raw_question and raw_question["text_segments"] is None:
            raise ValueError(f"{prefix}.text_segments must be a non-empty list, not null.")
        text_segments = normalize_text_segments(text, raw_question.get("text_segments"))
        text_segments = normalize_ai_formula_segments(text_segments)
        text = segments_plain_text(text_segments)

        return AIGeneratedQuestionDTO(
            question_type=question_type,
            text_segments=text_segments,
            title=title,
            text=text,
            instruction=instruction,
            content=content,
            answer_key=answer_key,
            grading_settings=grading_settings,
            difficulty=difficulty,
            max_score=max_score,
            learning_objective_ids=(
                learning_objective_ids
            ),
            explanation=explanation,
        )

    # ============================================================
    # ENUMS
    # ============================================================

    @staticmethod
    def _parse_question_type(
        value: Any,
        *,
        prefix: str,
    ) -> AssessmentQuestionType:
        if not isinstance(value, str):
            raise ValueError(
                f"{prefix}.question_type "
                "должен быть string."
            )

        try:
            return AssessmentQuestionType(value.strip().lower())
        except ValueError as exc:
            raise ValueError(
                f"{prefix}.question_type содержит "
                f"неизвестное значение: {value!r}."
            ) from exc

    @staticmethod
    def _parse_difficulty(
        value: Any,
        *,
        prefix: str,
    ) -> AssessmentQuestionDifficulty:
        if not isinstance(value, str):
            raise ValueError(
                f"{prefix}.difficulty "
                "должен быть string."
            )

        try:
            return AssessmentQuestionDifficulty(value)
        except ValueError as exc:
            raise ValueError(
                f"{prefix}.difficulty содержит "
                f"неизвестное значение: {value!r}."
            ) from exc

    # ============================================================
    # LEARNING OBJECTIVES
    # ============================================================

    @staticmethod
    def _parse_learning_objective_ids(
        value: Any,
        *,
        request: AIQuestionGenerationRequestDTO,
        prefix: str,
    ) -> tuple[int, ...]:
        if not isinstance(value, list):
            raise ValueError(
                f"{prefix}.learning_objective_ids "
                "должен быть list."
            )

        allowed_ids = {
            objective.learning_objective_id
            for objective in request.objectives
        }

        result: list[int] = []
        seen: set[int] = set()

        for objective_id in value:
            # bool нельзя принимать как int.
            if (
                isinstance(objective_id, bool)
                or not isinstance(objective_id, int)
            ):
                raise ValueError(
                    f"{prefix}.learning_objective_ids "
                    "должен содержать только int."
                )

            if objective_id in seen:
                raise ValueError(
                    f"{prefix}.learning_objective_ids "
                    f"содержит duplicate ID "
                    f"{objective_id}."
                )

            if objective_id not in allowed_ids:
                raise ValueError(
                    f"{prefix} ссылается на "
                    "learning_objective_id, которого "
                    f"нет в request: {objective_id}."
                )

            seen.add(objective_id)
            result.append(objective_id)

        return tuple(result)

    # ============================================================
    # TOTALS
    # ============================================================

    @classmethod
    def _validate_response_totals(
        cls,
        *,
        response: AIQuestionGenerationResponseDTO,
        request: AIQuestionGenerationRequestDTO,
    ) -> None:
        if len(response.questions) != request.question_count:
            raise ValueError(
                "AI вернул неправильное количество вопросов: "
                f"expected={request.question_count}, "
                f"actual={len(response.questions)}."
            )

        actual_max_score = sum(
            (
                question.max_score
                for question in response.questions
            ),
            Decimal("0"),
        )

        if actual_max_score != request.max_score:
            raise ValueError(
                "AI вернул неправильный общий max_score: "
                f"expected={request.max_score}, "
                f"actual={actual_max_score}."
            )

        expected_type_counts = {
            item.question_type: item.question_count
            for item in request.question_types
        }

        actual_type_counts: dict[
            AssessmentQuestionType,
            int,
        ] = {}

        for question in response.questions:
            actual_type_counts[question.question_type] = (
                actual_type_counts.get(
                    question.question_type,
                    0,
                )
                + 1
            )

        if actual_type_counts != expected_type_counts:
            raise ValueError(
                "AI нарушил распределение question_type: "
                f"expected={expected_type_counts}, "
                f"actual={actual_type_counts}."
            )

    # ============================================================
    # WARNINGS
    # ============================================================

    @staticmethod
    def _parse_warnings(
        value: Any,
    ) -> tuple[str, ...]:
        if not isinstance(value, list):
            raise ValueError(
                "AI response.warnings должен быть list."
            )

        result: list[str] = []

        for warning in value:
            if not isinstance(warning, str):
                raise ValueError(
                    "AI response.warnings должен "
                    "содержать только string."
                )

            warning = warning.strip()

            if warning:
                result.append(warning)

        return tuple(result)

    # ============================================================
    # SCALAR HELPERS
    # ============================================================

    @staticmethod
    def _require_non_empty_string(
        value: Any,
        *,
        field: str,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"{field} должен быть string."
            )

        value = value.strip()

        if not value:
            raise ValueError(
                f"{field} не должен быть пустым."
            )

        return value

    @staticmethod
    def _optional_string(
        value: Any,
        *,
        field: str,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                f"{field} должен быть string или null."
            )

        value = value.strip()

        return value or None

    @staticmethod
    def _require_dict(
        value: Any,
        *,
        field: str,
    ) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError(
                f"{field} должен быть object."
            )

        return value

    @staticmethod
    def _parse_positive_decimal(
        value: Any,
        *,
        field: str,
    ) -> Decimal:
        if isinstance(value, bool):
            raise ValueError(
                f"{field} должен быть числом > 0."
            )

        if not isinstance(
            value,
            (int, float, str, Decimal),
        ):
            raise ValueError(
                f"{field} должен быть числом > 0."
            )

        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(
                f"{field} содержит некорректное число."
            ) from exc

        if not result.is_finite():
            raise ValueError(
                f"{field} должен быть конечным числом."
            )

        if result <= 0:
            raise ValueError(
                f"{field} должен быть > 0."
            )

        return result
    