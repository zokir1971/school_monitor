# app/modules/assessment/services/ai_question_generator_service.py
from __future__ import annotations

from dataclasses import dataclass
from app.modules.assessment.helpers.ai_question_contract import normalize_text_segments, segments_plain_text

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.ai.question_provider import AIQuestionProvider
from app.modules.assessment.ai.question_validation_pipeline import (
    AIQuestionValidationPipeline,
)
from app.modules.assessment.enums import (
    AssessmentQuestionType,
    QuestionBankItemOrigin,
    QuestionBankItemStatus,
)
from app.modules.assessment.models import (
    LearningObjective,
    QuestionBankItem,
    QuestionBankItemObjective,
)
from app.modules.assessment.repositories.question_bank_repo import (
    QuestionBankRepo,
)
from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIGeneratedQuestionDTO,
    AIQuestionGenerationRequestDTO,
    AIQuestionGenerationResponseDTO,
)


@dataclass(slots=True, frozen=True)
class AIGeneratedQuestionBankResult:
    """
    Результат атомарного сохранения AI generation batch.
    """

    item_ids: tuple[int, ...]
    warnings: tuple[str, ...]


class AIQuestionGeneratorService:
    """
    Application service для материализации технически
    проверенного AI response в Question Bank.

    Гарантии:
    - все AI-вопросы проходят Question Contract validation;
    - все LearningObjective загружаются одним запросом;
    - SQL-запросов внутри question/objective loops нет;
    - все QuestionBankItem создаются как AI_GENERATED / DRAFT;
    - batch сохраняется атомарно;
    - один commit на весь batch;
    - при любой ошибке выполняется rollback всего batch.
    """

    @classmethod
    async def generate_and_save(
        cls,
        db: AsyncSession,
        *,
        provider: AIQuestionProvider,
        request: AIQuestionGenerationRequestDTO,
        created_by_user_id: int | None,
    ) -> AIGeneratedQuestionBankResult:
        """
        Полный application flow AI generation.

        Provider:
            генерирует структурированный response.

        Persistence flow:
            валидирует response;
            проверяет LearningObjective;
            создаёт QuestionBankItem;
            создаёт objective links;
            выполняет одну транзакцию сохранения.

        Provider не имеет доступа к DB/session.
        """

        response = await provider.generate_questions(
            request
        )

        return await cls.save_generated_questions(
            db,
            request=request,
            response=response,
            created_by_user_id=created_by_user_id,
        )

    @classmethod
    async def save_generated_questions(
            cls,
            db: AsyncSession,
            *,
            request: AIQuestionGenerationRequestDTO,
            response: AIQuestionGenerationResponseDTO,
            created_by_user_id: int | None,
    ) -> AIGeneratedQuestionBankResult:
        """
        Transaction-owning facade.

        Сохраняет полный AI generation batch атомарно
        и самостоятельно завершает транзакцию.

        Этот контракт сохраняется для существующих callers
        и CASE 60-64.
        """

        try:
            result = (
                await cls.save_generated_questions_in_transaction(
                    db,
                    request=request,
                    response=response,
                    created_by_user_id=created_by_user_id,
                )
            )

            await db.commit()

            return result

        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def save_generated_questions_in_transaction(
            cls,
            db: AsyncSession,
            *,
            request: AIQuestionGenerationRequestDTO,
            response: AIQuestionGenerationResponseDTO,
            created_by_user_id: int | None,
    ) -> AIGeneratedQuestionBankResult:
        """
        Сохраняет AI generation batch внутри транзакции caller.

        ВАЖНО:
            - COMMIT здесь запрещён;
            - ROLLBACK здесь запрещён;
            - transaction ownership принадлежит caller;
            - repository выполняет только необходимые
              SELECT / INSERT / FLUSH.

        Используется orchestration-сервисами, которым нужно
        атомарно объединить сохранение вопросов с другими
        изменениями состояния.
        """

        # ----------------------------------------------------
        # 1. Повторная техническая защита перед persistence.
        # ----------------------------------------------------

        image_refs = {segment['object_key']: segment for question in response.questions
                      for segment in question.text_segments if segment.get('type') == 'image'}
        for question in response.questions:
            if question.question_type == AssessmentQuestionType.IMAGE_CHOICE:
                for option in question.content.get('options', []):
                    image_refs[option['object_key']] = dict(option, type='image')
        if image_refs:
            from app.core.storage.factory import get_storage
            from app.modules.assessment.services.question_bank_media_service import QuestionBankMediaService
            await QuestionBankMediaService(get_storage()).validate_references(
                list(image_refs.values()), user_id=created_by_user_id)

        validation_result = (
            AIQuestionValidationPipeline.validate(
                response
            )
        )

        questions = validation_result.questions

        if len(questions) != request.question_count:
            raise ValueError(
                "Generated question count does not match "
                "generation request."
            )

        # ----------------------------------------------------
        # 2. Generated DTO <-> request boundary.
        # ----------------------------------------------------

        cls._validate_generation_boundary(
            request=request,
            questions=questions,
        )

        # ----------------------------------------------------
        # 3. Собираем ВСЕ LearningObjective IDs.
        # ----------------------------------------------------

        learning_objective_ids = (
            cls._collect_learning_objective_ids(
                questions
            )
        )

        # РОВНО один SELECT, если IDs существуют.
        learning_objectives = (
            await QuestionBankRepo
            .get_learning_objectives_by_ids(
                db,
                learning_objective_ids=(
                    learning_objective_ids
                ),
            )
        )

        # ----------------------------------------------------
        # 4. Проверяем LearningObjective.
        #
        # Только Python.
        # ----------------------------------------------------

        cls._validate_learning_objectives(
            request=request,
            requested_ids=learning_objective_ids,
            learning_objectives=learning_objectives,
        )

        # ----------------------------------------------------
        # 5. Строим QuestionBankItem.
        #
        # Только Python.
        # ----------------------------------------------------

        items = [
            cls._build_bank_item(
                request=request,
                question=question,
                created_by_user_id=(
                    created_by_user_id
                ),
            )
            for question in questions
        ]

        # ----------------------------------------------------
        # 6. Batch INSERT + FLUSH.
        # ----------------------------------------------------

        items = await QuestionBankRepo.add_many(
            db,
            items=items,
        )

        # ----------------------------------------------------
        # 7. Строим objective links.
        #
        # SQL внутри циклов отсутствует.
        # ----------------------------------------------------

        objective_links = (
            cls._build_objective_links(
                items=items,
                questions=questions,
            )
        )

        # ----------------------------------------------------
        # 8. Batch INSERT objective links + FLUSH.
        # ----------------------------------------------------

        await QuestionBankRepo.add_objectives(
            db,
            objectives=objective_links,
        )

        # ----------------------------------------------------
        # 9. NO COMMIT.
        #
        # Transaction принадлежит caller.
        # ----------------------------------------------------

        return AIGeneratedQuestionBankResult(
            item_ids=tuple(
                item.id
                for item in items
            ),
            warnings=validation_result.warnings,
        )
    # ============================================================
    # GENERATION BOUNDARY
    # ============================================================

    @staticmethod
    def _validate_generation_boundary(
        *,
        request: AIQuestionGenerationRequestDTO,
        questions: tuple[AIGeneratedQuestionDTO, ...],
    ) -> None:
        allowed_objective_ids = {
            objective.learning_objective_id
            for objective in request.objectives
        }

        expected_type_counts = {
            item.question_type: item.question_count
            for item in request.question_types
        }

        actual_type_counts = {
            question_type: 0
            for question_type in expected_type_counts
        }

        total_score = sum(
            (
                question.max_score
                for question in questions
            ),
            start=request.max_score * 0,
        )

        if total_score != request.max_score:
            raise ValueError(
                "Generated questions max_score does not "
                "match generation request."
            )

        for question in questions:
            if (
                question.question_type
                not in expected_type_counts
            ):
                raise ValueError(
                    "Generated question_type is not "
                    "allowed by generation request: "
                    f"{question.question_type.value}."
                )

            actual_type_counts[
                question.question_type
            ] += 1

            objective_ids = (
                question.learning_objective_ids
            )

            if len(objective_ids) != len(
                set(objective_ids)
            ):
                raise ValueError(
                    "Generated question contains duplicate "
                    "learning_objective_id."
                )

            if allowed_objective_ids and not objective_ids:
                raise ValueError("Generated question must reference a requested learning objective.")

            unknown_ids = (
                set(objective_ids)
                - allowed_objective_ids
            )

            if unknown_ids:
                raise ValueError(
                    "Generated question references "
                    "LearningObjective outside generation "
                    "request: "
                    + ", ".join(
                        str(objective_id)
                        for objective_id
                        in sorted(unknown_ids)
                    )
                )

        for requested_type in request.question_types:
            actual_score = sum((q.max_score for q in questions if q.question_type == requested_type.question_type), start=request.max_score * 0)
            if actual_score != requested_type.max_score:
                raise ValueError("Generated score distribution by question type does not match request.")

        if actual_type_counts != expected_type_counts:
            raise ValueError(
                "Generated question type distribution "
                "does not match generation request."
            )

    # ============================================================
    # LEARNING OBJECTIVES
    # ============================================================

    @staticmethod
    def _collect_learning_objective_ids(
        questions: tuple[AIGeneratedQuestionDTO, ...],
    ) -> list[int]:
        return sorted(
            {
                objective_id
                for question in questions
                for objective_id
                in question.learning_objective_ids
            }
        )

    @staticmethod
    def _validate_learning_objectives(
        *,
        request: AIQuestionGenerationRequestDTO,
        requested_ids: list[int],
        learning_objectives: list[LearningObjective],
    ) -> None:
        if not requested_ids:
            return

        loaded_by_id = {
            objective.id: objective
            for objective in learning_objectives
        }

        missing_ids = [
            objective_id
            for objective_id in requested_ids
            if objective_id not in loaded_by_id
        ]

        if missing_ids:
            raise ValueError(
                "LearningObjective not found: "
                + ", ".join(
                    str(objective_id)
                    for objective_id in missing_ids
                )
            )

        tracks = {getattr(loaded_by_id[key], "education_track", "") for key in requested_ids}
        if len(tracks) > 1:
            raise ValueError("Learning objectives belong to different education tracks.")
        for objective_id in requested_ids:
            objective = loaded_by_id[objective_id]

            if objective.subject_id != request.subject_id:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "belongs to another subject."
                )

            if (
                objective.grade_level
                != request.grade_level
            ):
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "belongs to another grade level."
                )

            if not objective.is_active:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "is inactive."
                )

    # ============================================================
    # BANK ITEMS
    # ============================================================

    @staticmethod
    def _build_bank_item(
        *,
        request: AIQuestionGenerationRequestDTO,
        question: AIGeneratedQuestionDTO,
        created_by_user_id: int | None,
    ) -> QuestionBankItem:
        return QuestionBankItem(
            subject_id=request.subject_id,
            grade_level=request.grade_level,

            question_type=question.question_type,
            difficulty=question.difficulty,
            language=request.language,

            status=QuestionBankItemStatus.DRAFT,
            origin=QuestionBankItemOrigin.AI_GENERATED,

            title=(
                question.title.strip()
                if question.title
                and question.title.strip()
                else None
            ),

            text=segments_plain_text(normalize_text_segments(question.text, question.text_segments, allow_images=True)),
            text_segments=list(normalize_text_segments(question.text, question.text_segments, allow_images=True)),

            instruction=(
                question.instruction.strip()
                if question.instruction
                and question.instruction.strip()
                else None
            ),

            content=dict(question.content),
            answer_key=dict(question.answer_key),

            grading_settings=dict(
                question.grading_settings
            ),

            max_score=question.max_score,

            explanation=(
                question.explanation.strip()
                if question.explanation
                and question.explanation.strip()
                else None
            ),

            # Позже 8.7 / 8.8 сможет использовать это поле
            # для внутреннего комментария эксперта.
            author_comment=None,

            created_by_user_id=created_by_user_id,
        )

    # ============================================================
    # OBJECTIVE LINKS
    # ============================================================

    @staticmethod
    def _build_objective_links(
        *,
        items: list[QuestionBankItem],
        questions: tuple[AIGeneratedQuestionDTO, ...],
    ) -> list[QuestionBankItemObjective]:
        if len(items) != len(questions):
            raise ValueError(
                "QuestionBankItem batch is inconsistent "
                "with generated question batch."
            )

        links: list[QuestionBankItemObjective] = []

        for item, question in zip(
            items,
            questions,
            strict=True,
        ):
            for order_no, objective_id in enumerate(
                question.learning_objective_ids,
                start=1,
            ):
                links.append(
                    QuestionBankItemObjective(
                        question_bank_item_id=item.id,
                        learning_objective_id=(
                            objective_id
                        ),
                        order_no=order_no,
                    )
                )

        return links
