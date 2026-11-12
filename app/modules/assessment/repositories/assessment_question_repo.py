# app/modules/assessment/repositories/assessment_question_repo.py

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AssessmentQuestionType,
)
from app.modules.assessment.models import (
    Assessment,
    AssessmentQuestion,
)


@dataclass(frozen=True, slots=True)
class OnlineAssessmentQuestionRow:
    """
    Безопасная строка вопроса для online execution.

    Намеренно НЕ содержит:

        answer_key
        grading_settings

    Поэтому даже если Service Layer передаст
    эту структуру дальше в DTO / route,
    правильный ответ ученику не утечёт.
    """

    question_id: int
    assessment_id: int

    assessment_objective_id: int | None

    question_type: AssessmentQuestionType

    text: str
    instruction: str | None

    max_score: Decimal
    order_no: int

    content: dict[str, Any]

    is_required: bool


class AssessmentQuestionRepo:
    """
    Репозиторий заданий Assessment.

    Отвечает только за SQL / ORM операции
    с AssessmentQuestion.

    Здесь нет:
        - проверки статусов Assessment;
        - проверки ONLINE / MANUAL;
        - проверки готовности Assessment;
        - проверки ответов ученика;
        - расчёта баллов;
        - commit.

    Бизнес-логика находится в Service Layer.
    """

    # =========================================================
    # CREATE
    # =========================================================

    @staticmethod
    async def add_many(
        db: AsyncSession,
        *,
        questions: Sequence[AssessmentQuestion],
    ) -> list[AssessmentQuestion]:
        """
        Добавить несколько заданий одним batch-вызовом.

        commit выполняет Service Layer.
        """

        items = list(questions)

        if not items:
            return []

        db.add_all(items)

        await db.flush()

        return items

    # =========================================================
    # GET BY ID
    # =========================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        question_id: int,
    ) -> AssessmentQuestion | None:
        """
        Получить вопрос по primary key.

        Метод не выполняет assessment / school boundary.
        Для пользовательских операций использовать
        get_for_assessment().
        """

        stmt = (
            select(AssessmentQuestion)
            .where(
                AssessmentQuestion.id
                == question_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =========================================================
    # ASSESSMENT BOUNDARY
    # =========================================================

    @staticmethod
    async def get_for_assessment(
        db: AsyncSession,
        *,
        question_id: int,
        assessment_id: int,
        school_id: int,
    ) -> AssessmentQuestion | None:
        """
        Получить вопрос конкретного Assessment
        внутри конкретной школы.

        Security boundary:

            AssessmentQuestion
                -> Assessment

        Проверяются:
            question_id
            assessment_id
            school_id
        """

        stmt = (
            select(AssessmentQuestion)
            .join(
                Assessment,
                Assessment.id
                == AssessmentQuestion.assessment_id,
            )
            .where(
                AssessmentQuestion.id
                == question_id,

                AssessmentQuestion.assessment_id
                == assessment_id,

                Assessment.id
                == assessment_id,

                Assessment.school_id
                == school_id,
            )
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =========================================================
    # ALL QUESTIONS
    # =========================================================

    @staticmethod
    async def get_many_for_assessment(
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
        include_inactive: bool = False,
    ) -> list[AssessmentQuestion]:
        """
        Получить задания Assessment внутри школы.

        Используется административными/service-flow,
        где разрешён полный ORM AssessmentQuestion,
        включая answer_key и grading_settings.

        Для student online execution использовать
        get_online_rows().
        """

        stmt = (
            select(AssessmentQuestion)
            .join(
                Assessment,
                Assessment.id
                == AssessmentQuestion.assessment_id,
            )
            .where(
                AssessmentQuestion.assessment_id
                == assessment_id,

                Assessment.id
                == assessment_id,

                Assessment.school_id
                == school_id,
            )
        )

        if not include_inactive:
            stmt = stmt.where(
                AssessmentQuestion.is_active.is_(True)
            )

        stmt = stmt.order_by(
            AssessmentQuestion.order_no.asc(),
            AssessmentQuestion.id.asc(),
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =========================================================
    # ONLINE EXECUTION
    # =========================================================

    @staticmethod
    async def get_online_rows(
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
    ) -> list[OnlineAssessmentQuestionRow]:
        """
        Получить активные задания для выполнения учеником.

        ВАЖНО:
        запрос намеренно НЕ выбирает:

            AssessmentQuestion.answer_key
            AssessmentQuestion.grading_settings

        Таким образом правильные ответы физически
        не попадают в результат SQL-запроса.

        Один SQL-запрос.
        """

        stmt = (
            select(
                AssessmentQuestion.id.label(
                    "question_id"
                ),
                AssessmentQuestion.assessment_id.label(
                    "assessment_id"
                ),
                AssessmentQuestion.assessment_objective_id.label(
                    "assessment_objective_id"
                ),
                AssessmentQuestion.question_type.label(
                    "question_type"
                ),
                AssessmentQuestion.text.label(
                    "text"
                ),
                AssessmentQuestion.instruction.label(
                    "instruction"
                ),
                AssessmentQuestion.max_score.label(
                    "max_score"
                ),
                AssessmentQuestion.order_no.label(
                    "order_no"
                ),
                AssessmentQuestion.content.label(
                    "content"
                ),
                AssessmentQuestion.is_required.label(
                    "is_required"
                ),
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentQuestion.assessment_id,
            )
            .where(
                AssessmentQuestion.assessment_id
                == assessment_id,

                Assessment.id
                == assessment_id,

                Assessment.school_id
                == school_id,

                AssessmentQuestion.is_active.is_(True),
            )
            .order_by(
                AssessmentQuestion.order_no.asc(),
                AssessmentQuestion.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return [
            OnlineAssessmentQuestionRow(
                question_id=row.question_id,
                assessment_id=row.assessment_id,
                assessment_objective_id=(
                    row.assessment_objective_id
                ),
                question_type=row.question_type,
                text=row.text,
                instruction=row.instruction,
                max_score=row.max_score,
                order_no=row.order_no,
                content=row.content,
                is_required=row.is_required,
            )
            for row in result.all()
        ]

    # =========================================================
    # COUNT / SCORE
    # =========================================================

    @staticmethod
    async def get_active_count(
            db: AsyncSession,
            *,
            assessment_id: int,
            school_id: int,
    ) -> int:
        """
        Количество активных заданий Assessment.

        Один SQL COUNT.
        """

        stmt = (
            select(
                func.count(
                    AssessmentQuestion.id
                )
            )
            .join(
                Assessment,
                Assessment.id
                == AssessmentQuestion.assessment_id,
            )
            .where(
                AssessmentQuestion.assessment_id
                == assessment_id,

                Assessment.id
                == assessment_id,

                Assessment.school_id
                == school_id,

                AssessmentQuestion.is_active.is_(True),
            )
        )

        result = await db.execute(stmt)

        return int(
            result.scalar_one()
        )
