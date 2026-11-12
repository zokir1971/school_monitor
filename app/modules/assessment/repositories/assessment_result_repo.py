# app/modules/assessment/repositories/assessment_result_repo.py

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import AssessmentGrade
from app.modules.assessment.models import AssessmentResult


@dataclass(frozen=True, slots=True)
class AssessmentResultWrite:
    """Подготовленные Service Layer данные итогового результата."""

    assessment_student_id: int
    score: Decimal
    max_score: Decimal
    percent: Decimal
    grade: AssessmentGrade
    calculated_at: datetime | None = None


class AssessmentResultRepo:
    """
    Репозиторий итоговых результатов Assessment.

    Проценты и оценки сюда приходят уже рассчитанными
    из AssessmentScoringService.

    Для пакетного сохранения используется upsert_many(),
    чтобы не создавать N+1 запросов.
    """

    @staticmethod
    async def get_by_assessment_student_id(
        db: AsyncSession,
        *,
        assessment_student_id: int,
    ) -> AssessmentResult | None:
        stmt = (
            select(AssessmentResult)
            .where(
                AssessmentResult.assessment_student_id
                == assessment_student_id,
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_many_by_student_ids(
        db: AsyncSession,
        *,
        assessment_student_ids: Sequence[int],
    ) -> list[AssessmentResult]:
        ids = tuple(dict.fromkeys(assessment_student_ids))

        if not ids:
            return []

        stmt = (
            select(AssessmentResult)
            .where(
                AssessmentResult.assessment_student_id.in_(ids)
            )
        )

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def upsert_many(
        cls,
        db: AsyncSession,
        *,
        items: Sequence[AssessmentResultWrite],
    ) -> dict[int, AssessmentResult]:
        """
        Пакетно создать/обновить итоговые результаты.

        SQL-профиль:
            1 SELECT существующих результатов;
            1 flush для всех INSERT/UPDATE.

        Никаких SELECT внутри цикла.
        """

        writes = list(items)

        if not writes:
            return {}

        student_ids = [
            item.assessment_student_id
            for item in writes
        ]

        if len(student_ids) != len(set(student_ids)):
            raise ValueError(
                "AssessmentResultWrite содержит "
                "дублирующиеся assessment_student_id."
            )

        existing = await cls.get_many_by_student_ids(
            db,
            assessment_student_ids=student_ids,
        )

        result_by_student_id = {
            result.assessment_student_id: result
            for result in existing
        }

        new_results: list[AssessmentResult] = []

        for item in writes:
            result = result_by_student_id.get(
                item.assessment_student_id
            )

            if result is None:
                result = AssessmentResult(
                    assessment_student_id=(
                        item.assessment_student_id
                    ),
                    score=item.score,
                    max_score=item.max_score,
                    percent=item.percent,
                    grade=item.grade,
                )

                if item.calculated_at is not None:
                    result.calculated_at = item.calculated_at

                new_results.append(result)
                result_by_student_id[
                    item.assessment_student_id
                ] = result

            else:
                result.score = item.score
                result.max_score = item.max_score
                result.percent = item.percent
                result.grade = item.grade

                if item.calculated_at is not None:
                    result.calculated_at = item.calculated_at

        if new_results:
            db.add_all(new_results)

        # Один flush после всех изменений. Для новых строк
        # здесь же будут получены primary key, нужные objective results.
        await db.flush()

        return result_by_student_id

    @staticmethod
    async def delete_many_by_student_ids(
        db: AsyncSession,
        *,
        assessment_student_ids: Sequence[int],
    ) -> int:
        """
        Пакетно удалить итоговые результаты участников.

        AssessmentObjectiveResult удаляются БД каскадно
        через FK assessment_result_id ON DELETE CASCADE.
        """

        ids = tuple(dict.fromkeys(assessment_student_ids))

        if not ids:
            return 0

        stmt = (
            delete(AssessmentResult)
            .where(
                AssessmentResult.assessment_student_id.in_(ids)
            )
        )

        result = await db.execute(stmt)
        await db.flush()

        return int(result.rowcount or 0)

    @classmethod
    async def upsert(
        cls,
        db: AsyncSession,
        *,
        assessment_student_id: int,
        score: Decimal,
        max_score: Decimal,
        percent: Decimal,
        grade: AssessmentGrade,
        calculated_at: datetime | None = None,
    ) -> AssessmentResult:
        """Одиночный API для сценариев, где пакет не требуется."""

        result_map = await cls.upsert_many(
            db,
            items=(
                AssessmentResultWrite(
                    assessment_student_id=assessment_student_id,
                    score=score,
                    max_score=max_score,
                    percent=percent,
                    grade=grade,
                    calculated_at=calculated_at,
                ),
            ),
        )

        return result_map[assessment_student_id]

    @staticmethod
    async def delete_by_assessment_student_id(
        db: AsyncSession,
        *,
        assessment_student_id: int,
    ) -> bool:
        """Одиночный API для сценариев, где пакет не требуется."""

        deleted = await AssessmentResultRepo.delete_many_by_student_ids(
            db,
            assessment_student_ids=(assessment_student_id,),
        )

        return deleted > 0
