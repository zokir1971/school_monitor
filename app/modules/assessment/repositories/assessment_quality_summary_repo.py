# app/modules/assessment/repositories/assessment_quality_summary_repo.py

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models import (
    AssessmentQualitySummary,
)


class AssessmentQualitySummaryRepo:
    """
    Repository аналитических snapshot-строк качества знаний.

    Не рассчитывает показатели.
    Не выполняет commit.

    Source of truth остаются AssessmentResult.
    """

    # =====================================================
    # GET
    # =====================================================

    @staticmethod
    async def get_by_group_id(
        db: AsyncSession,
        *,
        assessment_group_id: int,
    ) -> AssessmentQualitySummary | None:
        stmt = (
            select(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.assessment_group_id
                == assessment_group_id
            )
        )

        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_assessment_id(
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
    ) -> list[AssessmentQualitySummary]:
        """
        Все snapshot-строки одного Assessment.
        """

        stmt = (
            select(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.assessment_id
                == assessment_id,
                AssessmentQualitySummary.school_id
                == school_id,
            )
            .order_by(
                AssessmentQualitySummary.grade_level_snapshot.asc(),
                AssessmentQualitySummary.class_name_snapshot.asc(),
                AssessmentQualitySummary.id.asc(),
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    @staticmethod
    async def get_many_by_group_ids(
        db: AsyncSession,
        *,
        assessment_group_ids: Sequence[int],
    ) -> list[AssessmentQualitySummary]:
        ids = tuple(
            dict.fromkeys(
                assessment_group_ids
            )
        )

        if not ids:
            return []

        stmt = (
            select(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.assessment_group_id.in_(
                    ids
                )
            )
        )

        result = await db.execute(stmt)

        return list(
            result.scalars().all()
        )

    # =====================================================
    # WRITE
    # =====================================================

    @staticmethod
    async def add(
        db: AsyncSession,
        *,
        summary: AssessmentQualitySummary,
    ) -> AssessmentQualitySummary:
        db.add(summary)

        await db.flush()

        return summary

    @staticmethod
    async def add_many(
        db: AsyncSession,
        *,
        summaries: Sequence[
            AssessmentQualitySummary
        ],
    ) -> list[AssessmentQualitySummary]:
        items = list(
            summaries
        )

        if not items:
            return []

        db.add_all(
            items
        )

        await db.flush()

        return items

    # =====================================================
    # REPLACE
    # =====================================================

    @classmethod
    async def replace_for_assessment(
        cls,
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
        summaries: Sequence[
            AssessmentQualitySummary
        ],
    ) -> list[AssessmentQualitySummary]:
        """
        Полностью заменить snapshot одного Assessment.

        Используется:
            - при завершении Assessment;
            - при backfill;
            - при административном пересчёте.

        Сначала удаляются только summary этого Assessment,
        затем вставляется новый набор.

        commit выполняет Service Layer.
        """

        await cls.delete_by_assessment_id(
            db,
            assessment_id=assessment_id,
            school_id=school_id,
        )

        return await cls.add_many(
            db,
            summaries=summaries,
        )

    # =====================================================
    # DELETE
    # =====================================================

    @staticmethod
    async def delete_by_assessment_id(
        db: AsyncSession,
        *,
        assessment_id: int,
        school_id: int,
    ) -> int:
        """
        Удалить только аналитические snapshot-строки
        конкретного Assessment.

        Исходные AssessmentResult не затрагиваются.
        """

        stmt = (
            delete(
                AssessmentQualitySummary
            )
            .where(
                AssessmentQualitySummary.assessment_id
                == assessment_id,
                AssessmentQualitySummary.school_id
                == school_id,
            )
        )

        result = await db.execute(
            stmt
        )

        return int(
            result.rowcount or 0
        )
