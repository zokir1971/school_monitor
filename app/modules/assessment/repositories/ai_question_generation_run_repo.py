# app/modules/assessment/repositories/ai_question_generation_run_repo.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AIQuestionGenerationRunStatus,
)
from app.modules.assessment.models import (
    AIQuestionGenerationRun,
)


class AIQuestionGenerationRunRepo:
    """
    Repository для lifecycle AI question generation run.

    Repository отвечает только за работу с БД.

    Не отвечает за:
        - commit / rollback;
        - вызов AI provider;
        - бизнес-правила повторной генерации;
        - обработку стоимости API;
        - переходы lifecycle.

    Transaction ownership принадлежит service layer.
    """

    # =====================================================
    # CREATE
    # =====================================================

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        run: AIQuestionGenerationRun,
    ) -> AIQuestionGenerationRun:
        db.add(run)

        await db.flush()

        return run

    # =====================================================
    # GET BY ID
    # =====================================================

    @staticmethod
    async def get_by_id(
        db: AsyncSession,
        *,
        run_id: int,
    ) -> AIQuestionGenerationRun | None:
        stmt = select(
            AIQuestionGenerationRun
        ).where(
            AIQuestionGenerationRun.id == run_id
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =====================================================
    # GET RUNNING
    # =====================================================

    @staticmethod
    async def get_running_by_blueprint_id(
        db: AsyncSession,
        *,
        blueprint_id: int,
    ) -> AIQuestionGenerationRun | None:
        stmt = select(
            AIQuestionGenerationRun
        ).where(
            AIQuestionGenerationRun.blueprint_id
            == blueprint_id,
            AIQuestionGenerationRun.status
            == AIQuestionGenerationRunStatus.RUNNING,
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =====================================================
    # GET LATEST
    # =====================================================

    @staticmethod
    async def get_latest_by_blueprint_id(
        db: AsyncSession,
        *,
        blueprint_id: int,
    ) -> AIQuestionGenerationRun | None:
        stmt = (
            select(AIQuestionGenerationRun)
            .where(
                AIQuestionGenerationRun.blueprint_id
                == blueprint_id
            )
            .order_by(
                AIQuestionGenerationRun.started_at.desc(),
                AIQuestionGenerationRun.id.desc(),
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none()

    # =====================================================
    # HAS COMPLETED
    # =====================================================

    @staticmethod
    async def has_completed_for_blueprint(
        db: AsyncSession,
        *,
        blueprint_id: int,
    ) -> bool:
        stmt = (
            select(AIQuestionGenerationRun.id)
            .where(
                AIQuestionGenerationRun.blueprint_id
                == blueprint_id,
                AIQuestionGenerationRun.status
                == AIQuestionGenerationRunStatus.COMPLETED,
            )
            .limit(1)
        )

        result = await db.execute(stmt)

        return result.scalar_one_or_none() is not None

    # =====================================================
    # FLUSH
    # =====================================================

    @staticmethod
    async def flush(
        db: AsyncSession,
    ) -> None:
        await db.flush()
        