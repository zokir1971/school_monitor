# app/modules/assessment/repositories/assessment_objective_repo.py

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models import (
    AssessmentObjective,
    AssessmentObjectiveResult,
)


@dataclass(frozen=True, slots=True)
class AssessmentObjectiveResultWrite:
    """Подготовленные Service Layer данные результата по цели."""

    assessment_result_id: int
    assessment_objective_id: int
    score: Decimal
    max_score: Decimal
    percent: Decimal


class AssessmentObjectiveRepo:
    """
    Репозиторий структуры AssessmentObjective
    и результатов AssessmentObjectiveResult.

    Здесь нет:
        - расчётов;
        - бизнес-валидации;
        - commit.

    Для записи результатов используется batch replace_results(),
    поэтому сохранение не создаёт N+1 запросов.
    """

    # =====================================================
    # ASSESSMENT OBJECTIVES
    # =====================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        assessment_objective_id: int,
    ) -> AssessmentObjective | None:
        stmt = (
            select(AssessmentObjective)
            .where(
                AssessmentObjective.id
                == assessment_objective_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_many_by_assessment_id(
        db: AsyncSession,
        *,
        assessment_id: int,
    ) -> list[AssessmentObjective]:
        stmt = (
            select(AssessmentObjective)
            .where(
                AssessmentObjective.assessment_id
                == assessment_id,
            )
            .order_by(
                AssessmentObjective.order_no.asc(),
                AssessmentObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_many_by_ids_for_assessment(
        db: AsyncSession,
        *,
        assessment_id: int,
        assessment_objective_ids: Sequence[int],
    ) -> list[AssessmentObjective]:
        ids = tuple(dict.fromkeys(assessment_objective_ids))

        if not ids:
            return []

        stmt = (
            select(AssessmentObjective)
            .where(
                AssessmentObjective.assessment_id
                == assessment_id,
                AssessmentObjective.id.in_(ids),
            )
            .order_by(
                AssessmentObjective.order_no.asc(),
                AssessmentObjective.id.asc(),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    # =====================================================
    # OBJECTIVE RESULTS
    # =====================================================

    @staticmethod
    async def get_results_by_assessment_result_ids(
        db: AsyncSession,
        *,
        assessment_result_ids: Sequence[int],
    ) -> list[AssessmentObjectiveResult]:
        ids = tuple(dict.fromkeys(assessment_result_ids))

        if not ids:
            return []

        stmt = (
            select(AssessmentObjectiveResult)
            .where(
                AssessmentObjectiveResult.assessment_result_id.in_(ids)
            )
            .order_by(
                AssessmentObjectiveResult.assessment_result_id.asc(),
                AssessmentObjectiveResult.assessment_objective_id.asc(),
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def replace_results(
        db: AsyncSession,
        *,
        assessment_result_ids: Sequence[int],
        results: Sequence[AssessmentObjectiveResultWrite],
    ) -> list[AssessmentObjectiveResult]:
        """
        Пакетно полностью заменить objective results
        для набора AssessmentResult.

        SQL-профиль:
            1 DELETE по assessment_result_id IN (...);
            1 batch INSERT / flush для всех новых строк.

        Метод намеренно не делает SELECT и не выполняет
        запросов внутри циклов.
        """

        result_ids = tuple(
            dict.fromkeys(assessment_result_ids)
        )

        if not result_ids:
            if results:
                raise ValueError(
                    "Нельзя записать objective results без "
                    "assessment_result_ids."
                )
            return []

        allowed_result_ids = set(result_ids)
        writes = list(results)

        seen_pairs: set[tuple[int, int]] = set()

        for item in writes:
            if item.assessment_result_id not in allowed_result_ids:
                raise ValueError(
                    "AssessmentObjectiveResultWrite содержит "
                    "assessment_result_id вне заменяемого набора."
                )

            pair = (
                item.assessment_result_id,
                item.assessment_objective_id,
            )

            if pair in seen_pairs:
                raise ValueError(
                    "AssessmentObjectiveResultWrite содержит "
                    "дублирующую пару result/objective."
                )

            seen_pairs.add(pair)

        await db.execute(
            delete(AssessmentObjectiveResult)
            .where(
                AssessmentObjectiveResult.assessment_result_id.in_(
                    result_ids
                )
            )
        )

        entities = [
            AssessmentObjectiveResult(
                assessment_result_id=item.assessment_result_id,
                assessment_objective_id=item.assessment_objective_id,
                score=item.score,
                max_score=item.max_score,
                percent=item.percent,
            )
            for item in writes
        ]

        if entities:
            db.add_all(entities)

        await db.flush()

        return entities
