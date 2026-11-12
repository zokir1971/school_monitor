# app/modules/assessment/repositories/question_bank_repo.py
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
    QuestionBankItemOrigin,
    QuestionBankItemStatus,
)
from app.modules.assessment.models import (
    LearningObjective,
    QuestionBankItem,
    QuestionBankItemObjective, QuestionBankItemReview,
)


class QuestionBankRepo:
    """
    Repository для банка заданий Assessment.

    Repository отвечает только за доступ к данным.

    Бизнес-правила:
        - соответствие предмета;
        - соответствие класса;
        - активность LearningObjective;
        - допустимость переходов статусов;
        - валидация question contract

    проверяются на уровне Service.
    """

    # =========================================================
    # CREATE
    # =========================================================

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        item: QuestionBankItem,
    ) -> QuestionBankItem:
        db.add(item)
        await db.flush()

        return item

    @staticmethod
    async def add_many(
        db: AsyncSession,
        *,
        items: Sequence[QuestionBankItem],
    ) -> list[QuestionBankItem]:
        """
        Добавляет несколько QuestionBankItem одним batch-вызовом.

        Repository:
        - не выполняет commit;
        - не выполняет rollback;
        - не содержит бизнес-валидацию.

        После flush у элементов доступны primary key,
        необходимые для создания QuestionBankItemObjective.
        """

        bank_items = list(items)

        if not bank_items:
            return []

        db.add_all(bank_items)

        await db.flush()

        return bank_items
    # =========================================================
    # GET BY ID — LIGHT
    # =========================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        item_id: int,
    ) -> QuestionBankItem | None:
        stmt = (
            select(QuestionBankItem)
            .where(
                QuestionBankItem.id == item_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =========================================================
    # GET AGGREGATE
    # =========================================================

    @staticmethod
    async def get_aggregate_by_id(
        db: AsyncSession,
        *,
        item_id: int,
    ) -> QuestionBankItem | None:
        """
        Загружает QuestionBankItem вместе с данными,
        необходимыми для бизнес-логики и отображения.

        Загружаются:
            - Subject;
            - QuestionBankItemObjective;
            - LearningObjective.
        """

        stmt = (
            select(QuestionBankItem)
            .where(
                QuestionBankItem.id == item_id,
            )
            .options(
                selectinload(
                    QuestionBankItem.subject,
                ),
                selectinload(
                    QuestionBankItem.objectives,
                ).selectinload(
                    QuestionBankItemObjective.learning_objective,
                ),
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =========================================================
    # LIST / SEARCH
    # =========================================================

    @staticmethod
    async def get_many(
        db: AsyncSession,
        *,
        subject_id: int | None = None,
        grade_level: int | None = None,
        language: AssessmentLanguage | None = None,
        question_type: AssessmentQuestionType | None = None,
        difficulty: AssessmentQuestionDifficulty | None = None,
        status: QuestionBankItemStatus | None = None,
        origin: QuestionBankItemOrigin | None = None,
        created_by_user_id: int | None = None,
    ) -> list[QuestionBankItem]:
        stmt = select(QuestionBankItem)

        if subject_id is not None:
            stmt = stmt.where(
                QuestionBankItem.subject_id == subject_id,
            )

        if grade_level is not None:
            stmt = stmt.where(
                QuestionBankItem.grade_level == grade_level,
            )

        if language is not None:
            stmt = stmt.where(
                QuestionBankItem.language == language,
            )

        if question_type is not None:
            stmt = stmt.where(
                QuestionBankItem.question_type == question_type,
            )

        if difficulty is not None:
            stmt = stmt.where(
                QuestionBankItem.difficulty == difficulty,
            )

        if status is not None:
            stmt = stmt.where(
                QuestionBankItem.status == status,
            )

        if origin is not None:
            stmt = stmt.where(
                QuestionBankItem.origin == origin,
            )

        if created_by_user_id is not None:
            stmt = stmt.where(
                QuestionBankItem.created_by_user_id
                == created_by_user_id,
            )

        stmt = stmt.order_by(
            QuestionBankItem.created_at.desc(),
            QuestionBankItem.id.desc(),
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =========================================================
    # LEARNING OBJECTIVES
    # =========================================================

    @staticmethod
    async def get_learning_objectives(
        db: AsyncSession,
        *,
        subject_id: int,
        grade_level: int,
    ) -> list[LearningObjective]:
        """
        Возвращает активные LearningObjective
        конкретного предмета и класса.
        """

        stmt = (
            select(LearningObjective)
            .where(
                LearningObjective.subject_id == subject_id,
                LearningObjective.grade_level == grade_level,
                LearningObjective.is_active.is_(True),
            )
            .order_by(
                LearningObjective.code.asc(),
                LearningObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_learning_objectives_by_ids(
        db: AsyncSession,
        *,
        learning_objective_ids: Sequence[int],
    ) -> list[LearningObjective]:
        """
        Загружает LearningObjective по набору ID.

        Метод намеренно не проверяет предмет, класс
        и is_active — это ответственность Service.
        """

        if not learning_objective_ids:
            return []

        stmt = (
            select(LearningObjective)
            .where(
                LearningObjective.id.in_(
                    learning_objective_ids,
                )
            )
            .order_by(
                LearningObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =========================================================
    # OBJECTIVES
    # =========================================================

    @staticmethod
    async def add_objectives(
        db: AsyncSession,
        *,
        objectives: Sequence[QuestionBankItemObjective],
    ) -> None:
        if not objectives:
            return

        db.add_all(objectives)

        await db.flush()

    # =========================================================
    # FLUSH
    # =========================================================

    @staticmethod
    async def flush(
        db: AsyncSession,
    ) -> None:
        """
        Синхронизирует изменения aggregate с БД.

        Repository не владеет транзакцией:
        commit / rollback выполняет Service.
        """

        await db.flush()

    # =========================================================
    # HUMAN REVIEW
    # =========================================================

    @staticmethod
    async def add_review(
            db: AsyncSession,
            *,
            review: QuestionBankItemReview,
    ) -> QuestionBankItemReview:
        """
        Добавляет историческую запись экспертной проверки.

        Repository:
        - не проверяет lifecycle QuestionBankItem;
        - не изменяет QuestionBankItem.status;
        - не выполняет commit / rollback.

        После flush доступен review.id.
        """

        db.add(review)

        await db.flush()

        return review

    @staticmethod
    async def get_review_history(
        db: AsyncSession,
        *,
        item_id: int,
    ) -> list[QuestionBankItemReview]:
        """
        Возвращает историю экспертных проверок
        конкретного QuestionBankItem.

        reviewer_user загружается через selectinload,
        поэтому последующее обращение к
        review.reviewer_user не создаёт N+1.

        История возвращается от новой записи
        к более старой.
        """

        stmt = (
            select(QuestionBankItemReview)
            .where(
                QuestionBankItemReview.question_bank_item_id
                == item_id,
            )
            .options(
                selectinload(
                    QuestionBankItemReview.reviewer_user,
                ),
            )
            .order_by(
                QuestionBankItemReview.created_at.desc(),
                QuestionBankItemReview.id.desc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )
