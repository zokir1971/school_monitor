# app/modules/assessment/ai/question_quality_request_assembler.py
from __future__ import annotations

from app.modules.assessment.enums import AssessmentLanguage
from app.modules.assessment.models import (
    LearningObjective,
    QuestionBankItem,
    QuestionBankItemObjective,
)
from app.modules.assessment.schemas.ai_question_quality_review_dto import (
    AIQuestionQualityObjectiveDTO,
    AIQuestionQualityReviewRequestDTO,
)


class AIQuestionQualityRequestAssembler:
    """
    Собирает AIQuestionQualityReviewRequestDTO
    из заранее загруженного QuestionBankItem aggregate.

    Assembler:
    - не работает с БД;
    - не использует repository;
    - не выполняет SQL;
    - не вызывает AI;
    - не изменяет QuestionBankItem;
    - не управляет транзакцией.

    Ожидается, что aggregate заранее содержит:
    - QuestionBankItem.subject;
    - QuestionBankItem.objectives;
    - QuestionBankItemObjective.learning_objective.

    Для загрузки такого aggregate используется
    QuestionBankRepo.get_aggregate_by_id().
    """

    @classmethod
    def from_question_bank_item(
            cls,
            item: QuestionBankItem,
    ) -> AIQuestionQualityReviewRequestDTO:
        subject_name = cls._get_subject_name(
            item=item,
        )

        objectives = cls._build_objectives(
            links=item.objectives,
            language=item.language,
        )

        return AIQuestionQualityReviewRequestDTO(
            subject_id=item.subject_id,
            subject_name=subject_name,
            grade_level=item.grade_level,
            language=item.language,

            objectives=objectives,

            question_type=item.question_type,
            difficulty=item.difficulty,

            title=item.title,
            text=item.text,
            text_segments=tuple(item.text_segments or ()),
            instruction=item.instruction,

            content=item.content,
            answer_key=item.answer_key,
            grading_settings=item.grading_settings,

            max_score=item.max_score,
            explanation=item.explanation,
        )

    # ============================================================
    # OBJECTIVES
    # ============================================================

    @classmethod
    def _build_objectives(
            cls,
            links: list[QuestionBankItemObjective],
            *,
            language: str,
    ) -> tuple[AIQuestionQualityObjectiveDTO, ...]:
        ordered_links = sorted(
            links,
            key=lambda item: (
                item.order_no,
                item.id,
            ),
        )

        result: list[AIQuestionQualityObjectiveDTO] = []

        for objective_link in ordered_links:
            learning_objective: LearningObjective | None = (
                objective_link.learning_objective
            )

            if learning_objective is None:
                raise ValueError(
                    "QuestionBankItemObjective."
                    "learning_objective "
                    "не загружен или отсутствует."
                )

            objective_text = cls._get_objective_text(
                objective=learning_objective,
                language=language,
            )

            result.append(
                AIQuestionQualityObjectiveDTO(
                    learning_objective_id=learning_objective.id,
                    code=learning_objective.code,
                    text=objective_text,
                )
            )

        return tuple(result)
    # ============================================================
    # SUBJECT
    # ============================================================

    @staticmethod
    def _get_subject_name(
            item: QuestionBankItem,
    ) -> str:
        subject = item.subject

        if subject is None:
            raise ValueError(
                "QuestionBankItem.subject must be loaded "
                "before AI Quality Review."
            )

        if item.language == AssessmentLanguage.KAZAKH:
            name = subject.name_kz

        elif item.language == AssessmentLanguage.RUSSIAN:
            name = subject.name_ru or subject.name_kz

        elif item.language == AssessmentLanguage.ENGLISH:
            # В Subject отдельного английского названия нет.
            # Используем доступное локализованное название.
            name = subject.name_ru or subject.name_kz

        else:
            raise ValueError(
                "Unsupported assessment language: "
                f"{item.language!r}"
            )

        name = name.strip()

        if not name:
            raise ValueError(
                "Subject name must not be empty."
            )

        return name

    # ============================================================
    # LEARNING OBJECTIVE
    # ============================================================

    @staticmethod
    def _get_objective_text(
        *,
        objective: LearningObjective,
        language: str,
    ) -> str:
        """
        Выбирает текст LearningObjective
        согласно языку вопроса.

        kk -> title_kz
        ru -> title_ru

        Для en отдельного title_en в текущей модели нет,
        поэтому используется доступный текст цели.
        """

        if language == "kk":
            candidates = (
                objective.title_kz,
                objective.title_ru,
            )

        elif language == "ru":
            candidates = (
                objective.title_ru,
                objective.title_kz,
            )

        else:
            candidates = (
                objective.title_kz,
                objective.title_ru,
            )

        for candidate in candidates:
            if (
                isinstance(candidate, str)
                and candidate.strip()
            ):
                return candidate.strip()

        raise ValueError(
            "LearningObjective не содержит "
            "текста учебной цели."
        )
