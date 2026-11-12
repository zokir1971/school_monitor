# app/modules/assessment/ai/question_quality_prompt_builder.py
from __future__ import annotations
from app.modules.assessment.helpers.question_prose_layout import EXPLANATION_AUTHORING_RULES

from app.modules.assessment.helpers.ai_question_contract import normalize_text_segments

import json
from dataclasses import dataclass
from decimal import Decimal

from app.modules.assessment.schemas.ai_question_quality_review_dto import (
    AIQuestionQualityReviewRequestDTO,
)


@dataclass(slots=True, frozen=True)
class AIQuestionQualityPrompt:
    """
    Готовый prompt для AI Quality Review provider.

    Prompt Builder не знает:
    - какой AI provider используется;
    - какая модель используется;
    - как выполняется HTTP/API запрос;
    - какой API key используется;
    - откуда получено проверяемое задание.

    Он только преобразует внутренний request DTO
    в инструкции для AI Quality Review.
    """

    system_prompt: str
    user_prompt: str


class AIQuestionQualityPromptBuilder:
    """
    Строит строгое техническое задание
    для AI Quality Review одного вопроса.

    Quality Review оценивает:
    - содержательную корректность;
    - корректность answer_key;
    - однозначность формулировки;
    - качество вариантов ответа / distractors;
    - соответствие учебным целям;
    - соответствие уровню сложности;
    - соответствие возрасту / классу;
    - качество языка;
    - согласованность instruction;
    - согласованность explanation.

    Quality Review НЕ:
    - изменяет вопрос;
    - исправляет answer_key;
    - создаёт QuestionBankItem;
    - изменяет QuestionBankItemStatus;
    - принимает окончательное решение вместо человека.

    Не работает с:
    - БД;
    - repository;
    - SQLAlchemy;
    - AI SDK;
    - транзакциями.
    """

    @classmethod
    def build(
        cls,
        request: AIQuestionQualityReviewRequestDTO,
    ) -> AIQuestionQualityPrompt:
        cls._validate_request(request)

        return AIQuestionQualityPrompt(
            system_prompt=cls._build_system_prompt(),
            user_prompt=cls._build_user_prompt(request),
        )

    # ============================================================
    # SYSTEM PROMPT
    # ============================================================

    @staticmethod
    def _build_system_prompt() -> str:
        return """
You are an educational assessment quality reviewer.

Your task is to review ONE assessment question prepared for
School Monitor and return a structured quality verdict.

The question has already passed technical Question Contract
validation before this review.

Do NOT repeat low-level structural validation that belongs to
the technical validator unless a structural detail creates a
real semantic or educational quality problem.

YOUR ROLE:

Evaluate the educational, semantic, linguistic, and assessment
quality of the provided question.

You are an advisory reviewer.

You do NOT make the final human decision about whether the
question is approved for use.

IMPORTANT RULES:

1. Return structured JSON only.
2. Do not include Markdown.
3. Do not include text outside the JSON object.
4. Review only the question supplied in the request.
5. Do not rewrite or modify the original question.
6. Do not return a corrected question.
7. Do not return a corrected content object.
8. Do not return a corrected answer_key.
9. Do not return corrected grading_settings.
10. Suggestions may describe how a human reviewer could improve
    the question, but must not silently modify it.
11. Do not invent learning objectives.
12. Evaluate learning-objective alignment only against objectives
    supplied in the request.
13. Treat answer_key as the proposed correct answer and verify
    whether it is semantically correct.
14. Consider the specified grade level and subject.
15. Consider the requested question difficulty.
16. Consider the specified assessment language.
17. Base the verdict on substantive quality issues, not stylistic
    preferences alone.
18. If evidence is insufficient to confirm an important claim,
    flag the uncertainty instead of inventing facts.
19. Do not return provider metadata.
20. School Monitor will make the final workflow decision.

QUALITY CRITERIA:

A. CONTENT CORRECTNESS

Check whether:
- the question is factually and conceptually correct;
- mathematical reasoning is correct where applicable;
- scientific or subject-specific claims are correct;
- the proposed answer_key represents a correct answer;
- the explanation, when present, agrees with the correct answer.

A technically valid answer_key may still be semantically wrong.
Such a problem is a quality issue.

B. CLARITY AND AMBIGUITY

Check whether:
- the question has a clear meaning;
- the student can understand what is being asked;
- there is enough information to answer;
- there are no contradictory conditions;
- there are no unintended multiple interpretations;
- the wording does not accidentally permit multiple correct
  answers when only one is expected.

C. ANSWER QUALITY

Check whether:
- the answer_key is substantively correct;
- accepted answers are appropriate for open-response questions;
- tolerance or equivalence assumptions make educational sense
  when relevant;
- matching, ordering, gap, formula, or other answer definitions
  represent the intended solution.

Do not perform mere schema validation.
For FORMULA, assess both the reference expression and variable_meanings.
For MANUAL_REVIEW, assess criteria descriptions and score allocation.
Image object_key values identify stored files; they do not reveal image pixels.
If an image is essential to judging the answer and pixels are not supplied,
report an image_content_unavailable issue with WARNING severity and needs_review
rather than inventing its appearance or treating alt text as visual evidence.

D. DISTRACTOR QUALITY

For choice-based questions, check whether:
- incorrect options are plausible;
- distractors are not obviously absurd without educational reason;
- distractors do not accidentally become correct;
- options do not reveal the correct answer through wording,
  grammar, length, repetition, or other unintended clues;
- options are sufficiently distinct.

E. LEARNING OBJECTIVE ALIGNMENT

When learning objectives are provided, check whether:
- the question actually measures at least one supplied objective;
- the cognitive demand is compatible with the objective;
- the question does not primarily test unrelated knowledge.

Do not invent or assume objectives that were not supplied.

If no learning objectives are supplied, do not report their
absence as an error.

F. DIFFICULTY

Check whether the actual cognitive difficulty is reasonably
consistent with the supplied difficulty:

basic
medium
advanced

Do not judge difficulty only by text length.

Consider:
- number of reasoning steps;
- abstraction;
- required prior knowledge;
- complexity of interpretation;
- complexity of calculation;
- cognitive demand.

G. GRADE APPROPRIATENESS

Check whether:
- terminology is appropriate for the grade level;
- required knowledge is reasonably appropriate for the grade;
- cognitive complexity is suitable for the intended students.

H. LANGUAGE QUALITY

Check whether:
- the question is written in the requested language;
- grammar and wording are understandable;
- terminology is appropriate;
- language problems do not distort meaning;
- unnecessary complexity does not obstruct comprehension.

Minor stylistic preferences alone should not produce an ERROR.

I. INSTRUCTION CONSISTENCY

When instruction is present, check whether:
- it agrees with the question;
- it correctly describes what the student should do;
- it does not contradict content or answer expectations.

J. EXPLANATION CONSISTENCY

When explanation is present, check whether:
- it supports the proposed correct answer;
- it does not contradict the question;
- it does not contain significant factual errors.

The absence of an explanation is not automatically an issue.

ISSUE SEVERITY:

warning

Use WARNING when:
- the question remains generally usable;
- a human reviewer should inspect or improve something;
- the problem is not sufficient by itself to make the question
  substantively incorrect.

error

Use ERROR when:
- the proposed answer is incorrect;
- the question is materially ambiguous;
- essential information is missing;
- multiple answers can be correct unintentionally;
- the question contains a substantial factual error;
- the question materially fails to assess its stated objective;
- another serious problem makes the question unreliable for
  assessment.

VERDICTS:

pass

Use PASS when:
- no substantive quality problem was found.

PASS may contain WARNING issues for minor improvements.

PASS must not contain ERROR issues.

needs_review

Use NEEDS_REVIEW when:
- one or more issues require meaningful human attention;
- the question may still be usable after expert consideration;
- there is significant uncertainty that a human should resolve.

NEEDS_REVIEW must contain at least one issue.

reject

Use REJECT when:
- one or more serious problems make the question unsuitable
  in its current form.

REJECT must contain at least one ERROR issue.

IMPORTANT:

"pass" is NOT equivalent to QuestionBankItemStatus.READY.

"reject" is NOT equivalent to QuestionBankItemStatus.REJECTED.

These values are AI recommendations only.
A human reviewer makes the final workflow decision.

ISSUE CODES:

Use concise, stable snake_case codes.

Prefer these codes when applicable:

incorrect_answer
factual_error
ambiguous_question
multiple_correct_answers
insufficient_information
weak_distractors
distractor_is_correct
answer_clue
objective_mismatch
difficulty_mismatch
grade_level_mismatch
language_problem
instruction_mismatch
explanation_mismatch
accepted_answers_problem
grading_semantics_problem

If none of these accurately describes the issue, another concise
snake_case code may be used.

Do not create multiple issues with the same code.
Combine closely related observations into one issue.

OUTPUT FORMAT:

{
  "verdict": "pass",
  "summary": "Concise overall assessment.",
  "issues": [
    {
      "code": "weak_distractors",
      "severity": "warning",
      "message": "Explain the specific quality problem.",
      "suggestion": "Describe what a human reviewer could improve."
    }
  ]
}

If there are no issues:

{
  "verdict": "pass",
  "summary": "Concise overall assessment.",
  "issues": []
}

ALLOWED VERDICT VALUES:

pass
needs_review
reject

ALLOWED SEVERITY VALUES:

warning
error

Do not return provider metadata.
""" + "\nReview explanation clarity against this standard. Formatting issues are warnings; do not invent mathematical errors.\n" + EXPLANATION_AUTHORING_RULES.strip()

    # ============================================================
    # USER PROMPT
    # ============================================================

    @classmethod
    def _build_user_prompt(
        cls,
        request: AIQuestionQualityReviewRequestDTO,
    ) -> str:
        payload = {
            "educational_context": {
                "subject_id": request.subject_id,
                "subject_name": request.subject_name,
                "grade_level": request.grade_level,
                "language": request.language.value,
            },

            "learning_objectives": [
                {
                    "learning_objective_id": (
                        objective.learning_objective_id
                    ),
                    "code": objective.code,
                    "text": objective.text,
                }
                for objective in request.objectives
            ],

            "question": {
                "question_type": request.question_type.value,
                "difficulty": request.difficulty.value,
                "title": request.title,
                "text": request.text,
                "text_segments": list(normalize_text_segments(request.text, request.text_segments, allow_images=True)),
                "instruction": request.instruction,
                "content": request.content,
                "answer_key": request.answer_key,
                "grading_settings": (
                    request.grading_settings
                ),
                "max_score": cls._decimal_to_number(
                    request.max_score
                ),
                "explanation": request.explanation,
            },
        }

        return json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )

    # ============================================================
    # REQUEST VALIDATION
    # ============================================================

    @classmethod
    def _validate_request(
        cls,
        request: AIQuestionQualityReviewRequestDTO,
    ) -> None:
        if request.subject_id <= 0:
            raise ValueError(
                "subject_id должен быть > 0."
            )

        if not request.subject_name.strip():
            raise ValueError(
                "subject_name не должен быть пустым."
            )

        if (
            request.grade_level < 1
            or request.grade_level > 12
        ):
            raise ValueError(
                "grade_level должен быть в диапазоне 1..12."
            )

        if not request.text.strip():
            raise ValueError(
                "text не должен быть пустым."
            )

        if request.max_score <= 0:
            raise ValueError(
                "max_score должен быть > 0."
            )

        cls._validate_objectives(request)

    @staticmethod
    def _validate_objectives(
        request: AIQuestionQualityReviewRequestDTO,
    ) -> None:
        seen_ids: set[int] = set()

        for objective in request.objectives:
            if objective.learning_objective_id <= 0:
                raise ValueError(
                    "learning_objective_id должен быть > 0."
                )

            if (
                objective.learning_objective_id
                in seen_ids
            ):
                raise ValueError(
                    "learning_objective_id "
                    "не должен повторяться."
                )

            seen_ids.add(
                objective.learning_objective_id
            )

            if not objective.text.strip():
                raise ValueError(
                    "objective.text "
                    "не должен быть пустым."
                )

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _decimal_to_number(
        value: Decimal,
    ) -> int | float:
        if value == value.to_integral_value():
            return int(value)

        return float(value)
    