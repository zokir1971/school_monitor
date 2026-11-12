# app/modules/assessment/repositories/assessment_blueprint_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.assessment.enums import (
    AssessmentBlueprintStatus,
)
from app.modules.assessment.models import (
    AssessmentBlueprint,
    AssessmentBlueprintObjective,
    AssessmentBlueprintQuestionType,
    LearningObjective,
)


class AssessmentBlueprintRepo:
    """
    Репозиторий Assessment Blueprint.

    Отвечает только за работу с ORM / SQL:

        - создание Blueprint;
        - получение Blueprint;
        - получение полного aggregate;
        - выборку Blueprint по фильтрам;
        - получение LearningObjective;
        - добавление целей Blueprint;
        - добавление распределения типов заданий.

    Здесь нет:
        - проверки суммарного количества заданий;
        - проверки суммарного max_score;
        - проверки соответствия subject / grade;
        - управления статусами;
        - генерации Assessment;
        - commit.

    Бизнес-валидация и commit выполняются Service Layer.
    """

    # =====================================================
    # CREATE
    # =====================================================

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        blueprint: AssessmentBlueprint,
    ) -> AssessmentBlueprint:
        """
        Добавить AssessmentBlueprint
        в текущую транзакцию.

        commit выполняет Service Layer.
        """

        db.add(blueprint)

        await db.flush()

        return blueprint

    # =====================================================
    # GET
    # =====================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        blueprint_id: int,
    ) -> AssessmentBlueprint | None:
        """
        Получить Blueprint по первичному ключу.

        Relationships намеренно не загружаются.
        Использовать, когда требуется только сама сущность.
        """

        stmt = (
            select(AssessmentBlueprint)
            .where(
                AssessmentBlueprint.id
                == blueprint_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_aggregate_by_id(
        db: AsyncSession,
        *,
        blueprint_id: int,
    ) -> AssessmentBlueprint | None:
        """
        Получить полный Blueprint aggregate:

            Blueprint
                -> Subject
                -> Objectives
                    -> LearningObjective
                -> QuestionTypes

        Assessment здесь намеренно не загружаются.

        Метод подходит для:
            - просмотра Blueprint;
            - редактирования;
            - валидации;
            - последующего создания Assessment.

        Без lazy loading и N+1.
        """

        stmt = (
            select(AssessmentBlueprint)
            .where(
                AssessmentBlueprint.id
                == blueprint_id,
            )
            .options(
                selectinload(
                    AssessmentBlueprint.subject
                ),

                selectinload(
                    AssessmentBlueprint.objectives
                ).selectinload(
                    AssessmentBlueprintObjective.learning_objective
                ),

                selectinload(
                    AssessmentBlueprint.question_types
                ),
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =====================================================
    # LIST
    # =====================================================

    @staticmethod
    async def get_many(
        db: AsyncSession,
        *,
        subject_id: int | None = None,
        grade_level: int | None = None,
        status: AssessmentBlueprintStatus | None = None,
        created_by_user_id: int | None = None,
    ) -> list[AssessmentBlueprint]:
        """
        Получить список Blueprint с необязательными фильтрами.

        Relationships не загружаются, чтобы список
        оставался лёгким.

        Фильтры применяются только если переданы.
        """

        stmt = select(
            AssessmentBlueprint
        )

        if subject_id is not None:
            stmt = stmt.where(
                AssessmentBlueprint.subject_id
                == subject_id,
            )

        if grade_level is not None:
            stmt = stmt.where(
                AssessmentBlueprint.grade_level
                == grade_level,
            )

        if status is not None:
            stmt = stmt.where(
                AssessmentBlueprint.status
                == status,
            )

        if created_by_user_id is not None:
            stmt = stmt.where(
                AssessmentBlueprint.created_by_user_id
                == created_by_user_id,
            )

        stmt = stmt.order_by(
            AssessmentBlueprint.created_at.desc(),
            AssessmentBlueprint.id.desc(),
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =====================================================
    # LEARNING OBJECTIVES
    # =====================================================

    @staticmethod
    async def get_learning_objectives(
        db: AsyncSession,
        *,
        subject_id: int,
        grade_level: int,
    ) -> list[LearningObjective]:
        """
        Получить активные учебные цели
        конкретного предмета и класса.

        Используется Service Layer при построении
        и редактировании Blueprint.
        """

        stmt = (
            select(LearningObjective)
            .where(
                LearningObjective.subject_id
                == subject_id,

                LearningObjective.grade_level
                == grade_level,

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
        Получить учебные цели по набору ID.

        Repository намеренно не проверяет соответствие
        subject_id / grade_level Blueprint.

        Эту проверку выполняет Service Layer,
        сравнивая фактически полученные LearningObjective
        с параметрами Blueprint.
        """

        ids = tuple(
            dict.fromkeys(
                learning_objective_ids
            )
        )

        if not ids:
            return []

        stmt = (
            select(LearningObjective)
            .where(
                LearningObjective.id.in_(ids),
            )
            .order_by(
                LearningObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =====================================================
    # BLUEPRINT OBJECTIVES
    # =====================================================

    @staticmethod
    async def add_objectives(
        db: AsyncSession,
        *,
        objectives: Sequence[
            AssessmentBlueprintObjective
        ],
    ) -> list[AssessmentBlueprintObjective]:
        """
        Добавить цели Blueprint.

        Никакие aggregate-инварианты здесь
        не проверяются.
        """

        items = list(objectives)

        if not items:
            return []

        db.add_all(items)

        await db.flush()

        return items

    # =====================================================
    # BLUEPRINT QUESTION TYPES
    # =====================================================

    @staticmethod
    async def add_question_types(
        db: AsyncSession,
        *,
        question_types: Sequence[
            AssessmentBlueprintQuestionType
        ],
    ) -> list[AssessmentBlueprintQuestionType]:
        """
        Добавить распределение типов заданий Blueprint.

        Никакие aggregate-инварианты здесь
        не проверяются.
        """

        items = list(question_types)

        if not items:
            return []

        db.add_all(items)

        await db.flush()

        return items
