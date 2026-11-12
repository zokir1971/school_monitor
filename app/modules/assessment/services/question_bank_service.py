# app/modules/assessment/services/question_bank_service.py
from __future__ import annotations
from app.modules.assessment.helpers.element_scoring import policy_score, weighted

from decimal import Decimal
from dataclasses import replace
from app.modules.assessment.helpers.matching_score_policy import shuffle_new_matching
from app.modules.assessment.helpers.ordering_score_policy import shuffle_new_ordering

from app.modules.assessment.services.question_bank_media_service import validate_media_segment

from app.modules.assessment.helpers.manual_review_criteria import validate_manual_criteria

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.ai.question_quality_provider import AIQuestionQualityProvider
from app.modules.assessment.ai.question_quality_request_assembler import AIQuestionQualityRequestAssembler
from app.modules.assessment.enums import (
    AssessmentQuestionType, QuestionBankItemStatus, QuestionBankReviewDecision,
)
from app.modules.assessment.models import (
    LearningObjective,
    QuestionBankItem,
    QuestionBankItemObjective, QuestionBankItemReview,
)
from app.modules.assessment.repositories.question_bank_repo import (
    QuestionBankRepo,
)
from app.modules.assessment.helpers.multiple_choice_score_policy import validate_multiple_choice_score
from app.modules.assessment.helpers.true_false_score_policy import validate_true_false
from app.modules.assessment.helpers.number_score_policy import validate_number_parts
from app.modules.assessment.helpers.matching_score_policy import validate_matching_score
from app.modules.assessment.helpers.ordering_score_policy import validate_ordering_score
from app.modules.assessment.helpers.formula_score_policy import validate_formula_parts
from app.modules.assessment.helpers.fill_gaps_score_policy import validate_fill_gaps_score
from app.modules.assessment.schemas.ai_question_quality_review_dto import AIQuestionQualityReviewResultDTO
from app.modules.assessment.schemas.question_bank_dto import (
    QuestionBankItemCreateInput,
    QuestionBankItemCreateResult,
)
from app.modules.assessment.schemas.question_bank_review_dto import QuestionBankReviewCreateResult, \
    QuestionBankReviewHistoryItemDTO
from app.modules.assessment.services.ai_question_quality_review_service import AIQuestionQualityReviewService
from app.modules.assessment.services.assessment_question_validation_service import AssessmentQuestionValidationService


class QuestionBankService:
    """
    Бизнес-логика банка заданий Assessment.

    Service отвечает за:
        - generic validation;
        - проверку LearningObjective;
        - создание QuestionBankItem;
        - создание связей с LearningObjective;
        - транзакцию создания.

    Детальная проверка question contract по question_type
    будет реализована отдельно в Question Validation Engine.
    """

    # =========================================================
    # PUBLIC API
    # =========================================================

    @classmethod
    async def create_item(
            cls,
            db: AsyncSession,
            *,
            data: QuestionBankItemCreateInput,
            created_by_user_id: int | None,
    ) -> QuestionBankItemCreateResult:
        try:
            cls._validate_basic_fields(data)
            cls._validate_json_fields(data)
            if weighted(data.grading_settings):
                AssessmentQuestionValidationService.validate_authoring(question_type=data.question_type,content=data.content,
                    answer_key=data.answer_key,grading_settings=data.grading_settings,max_score=data.max_score)
            if data.question_type == AssessmentQuestionType.MULTIPLE_CHOICE:
                validate_multiple_choice_score(content=data.content, answer_key=data.answer_key,
                                               max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score))
            if data.question_type == AssessmentQuestionType.TRUE_FALSE:
                validate_true_false(data.content, data.answer_key, max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score))
            if data.question_type == AssessmentQuestionType.NUMBER:
                validate_number_parts(data.content, data.answer_key, data.grading_settings, max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score))
            if data.question_type == AssessmentQuestionType.MATCHING:
                validate_matching_score(data.content, data.answer_key, data.grading_settings, max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score))
                if data.grading_settings.get("matching_score_policy") == "per_pair_v1":
                    shuffled_content, shuffled_key = shuffle_new_matching(data.content, data.answer_key)
                    data = replace(data, content=shuffled_content, answer_key=shuffled_key)
            if data.question_type == AssessmentQuestionType.ORDERING:
                validate_ordering_score(data.content, data.answer_key, data.grading_settings, max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score))
                if data.grading_settings.get("ordering_score_policy") == "per_position_v1":
                    shuffled_content, shuffled_key = shuffle_new_ordering(data.content, data.answer_key)
                    data = replace(data, content=shuffled_content, answer_key=shuffled_key)
            if data.question_type == AssessmentQuestionType.FILL_GAPS:
                validate_fill_gaps_score(data.content, data.answer_key, data.grading_settings, max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score))
                if data.content.get("word_bank_format") == "rich_v1":
                    from app.modules.assessment.helpers.fill_gaps_rich_bank import shuffle_bank
                    data = replace(data, content=shuffle_bank(data.content))
            if data.question_type == AssessmentQuestionType.FORMULA:
                validate_formula_parts(data.content, data.answer_key, data.grading_settings, max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score))
                if data.grading_settings.get("formula_score_policy") == "per_part_v1":
                    from app.modules.assessment.helpers.formula_score_policy import shuffle_formula_options
                    data = replace(data, content=shuffle_formula_options(data.content))
            cls._validate_objective_inputs(data)

            learning_objectives = (
                await cls._load_and_validate_learning_objectives(
                    db,
                    data=data,
                )
            )

            item = QuestionBankItem(
                subject_id=data.subject_id,
                grade_level=data.grade_level,

                question_type=data.question_type,
                difficulty=data.difficulty,
                language=data.language,

                status=QuestionBankItemStatus.DRAFT,
                origin=data.origin,

                title=cls._normalize_optional_text(
                    data.title
                ),
                text=data.text.strip(),

                text_segments=[
                    dict(segment)
                    for segment in data.text_segments
                ],

                instruction=cls._normalize_optional_text(
                    data.instruction
                ),

                content=dict(data.content),
                answer_key=dict(data.answer_key),
                grading_settings=dict(
                    data.grading_settings
                ),

                max_score=data.max_score,

                explanation=cls._normalize_optional_text(
                    data.explanation
                ),
                author_comment=cls._normalize_optional_text(
                    data.author_comment
                ),

                created_by_user_id=created_by_user_id,
            )

            item = await QuestionBankRepo.create(
                db,
                item=item,
            )

            objective_links = cls._build_objective_links(
                item_id=item.id,
                data=data,
                learning_objectives=learning_objectives,
            )

            await QuestionBankRepo.add_objectives(
                db,
                objectives=objective_links,
            )

            await db.commit()

            return QuestionBankItemCreateResult(
                item_id=item.id,
            )

        except Exception:
            await db.rollback()
            raise

    # =========================================================
    # LIFECYCLE
    # =========================================================

    @classmethod
    async def submit_for_review(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
    ) -> None:
        """
        DRAFT -> REVIEW.

        Перед отправкой на review вопрос обязан иметь
        полностью валидный Question Contract.
        """

        try:
            item = await cls._get_aggregate_or_raise(
                db,
                item_id=item_id,
            )

            cls._require_status(
                item,
                expected=QuestionBankItemStatus.DRAFT,
            )

            cls._validate_item_for_review(item)
            from app.modules.assessment.services.bilingual_question_service import require_bilingual_ready
            await require_bilingual_ready(db,item,QuestionBankItemStatus.DRAFT)

            item.status = QuestionBankItemStatus.REVIEW

            await QuestionBankRepo.flush(db)
            await db.commit()

        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def approve(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
            reviewer_user_id: int,
            comment: str | None = None,
    ) -> QuestionBankReviewCreateResult:
        """
        Экспертное решение:

            REVIEW -> READY

        В одной транзакции:
            - повторно валидируется QuestionBankItem;
            - создаётся историческая запись review;
            - QuestionBankItem переводится в READY.

        reviewer_user_id определяется сервером
        по текущему авторизованному пользователю.
        """

        try:
            cls._validate_reviewer_user_id(
                reviewer_user_id
            )

            item = await cls._get_aggregate_or_raise(
                db,
                item_id=item_id,
            )

            cls._require_status(
                item,
                expected=QuestionBankItemStatus.REVIEW,
            )

            # Повторная защита перед READY.
            cls._validate_item_for_review(item)
            from app.modules.assessment.services.bilingual_question_service import require_bilingual_ready
            await require_bilingual_ready(db,item,QuestionBankItemStatus.REVIEW)

            review = QuestionBankItemReview(
                question_bank_item_id=item.id,
                reviewer_user_id=reviewer_user_id,
                decision=QuestionBankReviewDecision.APPROVED,
                comment=cls._normalize_optional_text(
                    comment
                ),
            )

            review = await QuestionBankRepo.add_review(
                db,
                review=review,
            )

            item.status = QuestionBankItemStatus.READY

            await QuestionBankRepo.flush(db)
            await db.commit()

            return QuestionBankReviewCreateResult(
                review_id=review.id,
                question_bank_item_id=item.id,
                decision=QuestionBankReviewDecision.APPROVED,
                item_status=QuestionBankItemStatus.READY,
            )

        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def reject(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
            reviewer_user_id: int,
            comment: str | None = None,
    ) -> QuestionBankReviewCreateResult:
        """
        Экспертное решение:

            REVIEW -> REJECTED

        В одной транзакции:
            - создаётся историческая запись review;
            - QuestionBankItem переводится в REJECTED.

        Для REJECTED повторная technical validation
        намеренно не выполняется: эксперт должен иметь
        возможность отклонить проблемный вопрос.
        """

        try:
            cls._validate_reviewer_user_id(
                reviewer_user_id
            )

            item = await cls._get_aggregate_or_raise(
                db,
                item_id=item_id,
            )

            cls._require_status(
                item,
                expected=QuestionBankItemStatus.REVIEW,
            )

            review = QuestionBankItemReview(
                question_bank_item_id=item.id,
                reviewer_user_id=reviewer_user_id,
                decision=QuestionBankReviewDecision.REJECTED,
                comment=cls._normalize_optional_text(
                    comment
                ),
            )

            review = await QuestionBankRepo.add_review(
                db,
                review=review,
            )

            item.status = QuestionBankItemStatus.REJECTED

            await QuestionBankRepo.flush(db)
            await db.commit()

            return QuestionBankReviewCreateResult(
                review_id=review.id,
                question_bank_item_id=item.id,
                decision=QuestionBankReviewDecision.REJECTED,
                item_status=QuestionBankItemStatus.REJECTED,
            )

        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def get_review_history(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
    ) -> list[QuestionBankReviewHistoryItemDTO]:
        """
        Возвращает историю экспертных решений
        по QuestionBankItem.

        Repository заранее загружает reviewer_user,
        поэтому преобразование ORM -> DTO
        не выполняет дополнительных SQL-запросов.
        """

        if item_id <= 0:
            raise ValueError(
                "item_id must be greater than 0."
            )

        reviews = await QuestionBankRepo.get_review_history(
            db,
            item_id=item_id,
        )

        return [
            cls._build_review_history_item(
                review
            )
            for review in reviews
        ]

    @classmethod
    async def return_to_draft(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
    ) -> None:
        """
        REJECTED -> DRAFT.

        После возврата автор может исправить вопрос
        и снова отправить его на review.
        """

        try:
            item = await cls._get_aggregate_or_raise(
                db,
                item_id=item_id,
            )

            cls._require_status(
                item,
                expected=QuestionBankItemStatus.REJECTED,
            )

            item.status = QuestionBankItemStatus.DRAFT

            await QuestionBankRepo.flush(db)
            await db.commit()

        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def archive(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
    ) -> None:
        """
        READY -> ARCHIVED.
        """

        try:
            item = await cls._get_aggregate_or_raise(
                db,
                item_id=item_id,
            )

            cls._require_status(
                item,
                expected=QuestionBankItemStatus.READY,
            )

            item.status = QuestionBankItemStatus.ARCHIVED

            await QuestionBankRepo.flush(db)
            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # =========================================================
    # BASIC VALIDATION
    # =========================================================

    @staticmethod
    def _validate_basic_fields(
            data: QuestionBankItemCreateInput,
    ) -> None:
        if data.subject_id <= 0:
            raise ValueError(
                "subject_id must be greater than 0."
            )

        if not 1 <= data.grade_level <= 12:
            raise ValueError(
                "grade_level must be between 1 and 12."
            )

        if not isinstance(data.text, str):
            raise ValueError(
                "text must be a string."
            )

        if not data.text.strip():
            raise ValueError(
                "Question text must not be empty."
            )

        if not isinstance(data.max_score, Decimal):
            raise ValueError(
                "max_score must be Decimal."
            )

        if data.max_score <= Decimal("0"):
            raise ValueError(
                "max_score must be greater than 0."
            )

    # =========================================================
    # JSON FIELDS
    # =========================================================

    @classmethod
    def _validate_json_fields(
            cls,
            data: QuestionBankItemCreateInput,
    ) -> None:
        cls._validate_text_segments(
            data.text_segments
        )
        if data.question_type.value == "manual_review":
            validate_manual_criteria(
                data.grading_settings.get("criteria"), max_score=policy_score(data.question_type.value,data.grading_settings,data.max_score),
            )

        if not isinstance(
                data.content,
                dict,
        ):
            raise ValueError(
                "content must be dict."
            )

        if not isinstance(
                data.answer_key,
                dict,
        ):
            raise ValueError(
                "answer_key must be dict."
            )

        if not isinstance(
                data.grading_settings,
                dict,
        ):
            raise ValueError(
                "grading_settings must be dict."
            )

    # =========================================================
    # OBJECTIVE INPUT VALIDATION
    # =========================================================

    @staticmethod
    def _validate_objective_inputs(
            data: QuestionBankItemCreateInput,
    ) -> None:
        if not data.objectives:
            return

        learning_objective_ids: set[int] = set()
        order_numbers: set[int] = set()

        for objective in data.objectives:
            if objective.learning_objective_id <= 0:
                raise ValueError(
                    "learning_objective_id "
                    "must be greater than 0."
                )

            if objective.order_no <= 0:
                raise ValueError(
                    "Objective order_no "
                    "must be greater than 0."
                )

            if (
                    objective.learning_objective_id
                    in learning_objective_ids
            ):
                raise ValueError(
                    "Duplicate LearningObjective "
                    "is not allowed."
                )

            if objective.order_no in order_numbers:
                raise ValueError(
                    "Duplicate objective order_no "
                    "is not allowed."
                )

            learning_objective_ids.add(
                objective.learning_objective_id
            )
            order_numbers.add(
                objective.order_no
            )

    # =========================================================
    # LEARNING OBJECTIVES
    # =========================================================

    @classmethod
    async def _load_and_validate_learning_objectives(
            cls,
            db: AsyncSession,
            *,
            data: QuestionBankItemCreateInput,
    ) -> list[LearningObjective]:
        if not data.objectives:
            return []

        requested_ids = [
            objective.learning_objective_id
            for objective in data.objectives
        ]

        learning_objectives = (
            await QuestionBankRepo.get_learning_objectives_by_ids(
                db,
                learning_objective_ids=requested_ids,
            )
        )

        cls._validate_learning_objectives(
            data=data,
            requested_ids=requested_ids,
            learning_objectives=learning_objectives,
        )

        return learning_objectives

    @staticmethod
    def _validate_learning_objectives(
            *,
            data: QuestionBankItemCreateInput,
            requested_ids: list[int],
            learning_objectives: list[LearningObjective],
    ) -> None:
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

        for objective_id in requested_ids:
            objective = loaded_by_id[objective_id]

            if objective.subject_id != data.subject_id:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "belongs to another subject."
                )

            if objective.grade_level != data.grade_level:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "belongs to another grade level."
                )

            if not objective.is_active:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "is inactive."
                )

    # =========================================================
    # BUILD OBJECTIVE LINKS
    # =========================================================

    @staticmethod
    def _build_objective_links(
            *,
            item_id: int,
            data: QuestionBankItemCreateInput,
            learning_objectives: list[LearningObjective],
    ) -> list[QuestionBankItemObjective]:
        if not data.objectives:
            return []

        # LearningObjective уже полностью проверены выше.
        # Здесь set используется как дополнительная защита
        # от рассинхронизации данных.
        loaded_ids = {
            objective.id
            for objective in learning_objectives
        }

        links: list[QuestionBankItemObjective] = []

        for objective_input in data.objectives:
            if (
                    objective_input.learning_objective_id
                    not in loaded_ids
            ):
                raise ValueError(
                    "Validated LearningObjective "
                    "is missing while building links."
                )

            links.append(
                QuestionBankItemObjective(
                    question_bank_item_id=item_id,
                    learning_objective_id=(
                        objective_input.learning_objective_id
                    ),
                    order_no=objective_input.order_no,
                )
            )

        return links

    # =========================================================
    # HELPERS
    # =========================================================
    @staticmethod
    def _validate_text_segments(
            segments: list[dict],
    ) -> None:
        if not isinstance(
                segments,
                list,
        ):
            raise ValueError(
                "text_segments must be list."
            )

        if not segments:
            raise ValueError(
                "text_segments must not be empty."
            )

        has_content = False

        for index, segment in enumerate(
                segments
        ):
            if not isinstance(
                    segment,
                    dict,
            ):
                raise ValueError(
                    "Each text_segments item "
                    "must be dict."
                )

            segment_type = segment.get(
                "type"
            )

            if segment_type == "image":
                try:
                    validate_media_segment(segment)
                except ValueError as exc:
                    raise ValueError(
                        f"text_segments[{index}]: {exc}"
                    ) from exc
                has_content = True
                continue

            if segment_type not in {
                "text",
                "latex",
            }:
                raise ValueError(
                    f"text_segments[{index}].type "
                    "must be 'text', 'latex' or 'image'."
                )

            value = segment.get(
                "text"
            )

            if not isinstance(
                    value,
                    str,
            ):
                raise ValueError(
                    f"text_segments[{index}].text "
                    "must be string."
                )

            if value.strip():
                has_content = True

        if not has_content:
            raise ValueError(
                "text_segments must contain "
                "non-empty content."
            )

    @staticmethod
    def _normalize_optional_text(
            value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        return normalized or None

    @staticmethod
    def _validate_reviewer_user_id(
            reviewer_user_id: int,
    ) -> None:
        if not isinstance(
                reviewer_user_id,
                int,
        ):
            raise ValueError(
                "reviewer_user_id must be int."
            )

        if reviewer_user_id <= 0:
            raise ValueError(
                "reviewer_user_id must be greater than 0."
            )

    @staticmethod
    def _build_review_history_item(
            review: QuestionBankItemReview,
    ) -> QuestionBankReviewHistoryItemDTO:
        reviewer = review.reviewer_user

        reviewer_name = (
            reviewer.full_name
            if reviewer is not None
            else None
        )

        return QuestionBankReviewHistoryItemDTO(
            review_id=review.id,
            reviewer_user_id=review.reviewer_user_id,
            reviewer_name=reviewer_name,
            decision=review.decision,
            comment=review.comment,
            created_at=review.created_at,
        )

    # =========================================================
    # LIFECYCLE HELPERS
    # =========================================================

    @staticmethod
    async def _get_aggregate_or_raise(
            db: AsyncSession,
            *,
            item_id: int,
    ) -> QuestionBankItem:
        if item_id <= 0:
            raise ValueError(
                "item_id must be greater than 0."
            )

        item = await QuestionBankRepo.get_aggregate_by_id(
            db,
            item_id=item_id,
        )

        if item is None:
            raise ValueError(
                f"QuestionBankItem not found: {item_id}"
            )

        return item

    @staticmethod
    def _require_status(
            item: QuestionBankItem,
            *,
            expected: QuestionBankItemStatus,
    ) -> None:
        if item.status != expected:
            raise ValueError(
                "Invalid QuestionBankItem status transition: "
                f"expected {expected.value}, "
                f"actual {item.status.value}."
            )

    @classmethod
    def _validate_item_for_review(
            cls,
            item: QuestionBankItem,
    ) -> None:
        """
        Полная доменная проверка перед REVIEW / READY.

        Здесь нет SQL-запросов.
        Aggregate должен быть полностью загружен Repository.
        """

        cls._validate_item_learning_objectives(
            item
        )

        cls._validate_text_segments(
            item.text_segments
        )

        if item.question_type.value == "manual_review":
            validate_manual_criteria(
                item.grading_settings.get("criteria"), max_score=item.max_score,
            )

        AssessmentQuestionValidationService.validate_authoring(
            question_type=item.question_type,
            content=item.content,
            answer_key=item.answer_key,
            grading_settings=item.grading_settings,
            max_score=item.max_score,
        )

    @staticmethod
    def _validate_item_learning_objectives(
            item: QuestionBankItem,
    ) -> None:
        """
        Проверяет уже загруженные relationships.

        Никаких Repository-вызовов внутри цикла.
        """

        seen_objective_ids: set[int] = set()
        seen_order_numbers: set[int] = set()

        for link in item.objectives:
            objective = link.learning_objective

            if objective is None:
                raise ValueError(
                    "QuestionBankItemObjective "
                    "has no LearningObjective."
                )

            if objective.id in seen_objective_ids:
                raise ValueError(
                    "Duplicate LearningObjective "
                    "is not allowed."
                )

            if link.order_no in seen_order_numbers:
                raise ValueError(
                    "Duplicate objective order_no "
                    "is not allowed."
                )

            if objective.subject_id != item.subject_id:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "belongs to another subject."
                )

            if objective.grade_level != item.grade_level:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "belongs to another grade level."
                )

            if not objective.is_active:
                raise ValueError(
                    f"LearningObjective {objective.id} "
                    "is inactive."
                )

            seen_objective_ids.add(
                objective.id
            )

            seen_order_numbers.add(
                link.order_no
            )

    # =========================================================
    # AI QUALITY REVIEW
    # =========================================================

    @classmethod
    async def review_quality(
            cls,
            db: AsyncSession,
            *,
            item_id: int,
            provider: AIQuestionQualityProvider,
    ) -> AIQuestionQualityReviewResultDTO:
        """
        Выполняет AI Quality Review сохранённого
        QuestionBankItem.

        AI Quality Review:
        - работает с полностью загруженным aggregate;
        - не выполняет дополнительные запросы в циклах;
        - не изменяет QuestionBankItem;
        - не изменяет QuestionBankItemStatus;
        - не выполняет commit / rollback;
        - не сохраняет verdict;
        - не исправляет вопрос автоматически.

        AI verdict является рекомендацией.
        """

        item = await cls._get_aggregate_or_raise(
            db,
            item_id=item_id,
        )

        # Domain validation relationships.
        # SQL здесь не выполняется:
        # relationships уже загружены repository.
        cls._validate_item_learning_objectives(
            item
        )

        request = (
            AIQuestionQualityRequestAssembler
            .from_question_bank_item(
                item
            )
        )

        review_service = AIQuestionQualityReviewService(
            provider=provider,
        )

        return await review_service.review(
            request
        )
