# app/modules/assessment/services/ai_question_generation_run_service.py
from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.enums import (
    AIQuestionGenerationRunStatus,
)
from app.modules.assessment.models import (
    AIQuestionGenerationRun,
)
from app.modules.assessment.repositories.ai_question_generation_run_repo import (
    AIQuestionGenerationRunRepo,
)


class AIQuestionGenerationRunService:
    """
    Управляет lifecycle одного AI question generation run.

    Поддерживаемые переходы:

        start:
            -> RUNNING

        complete:
            RUNNING -> COMPLETED

        fail:
            RUNNING -> FAILED

    Правила:
        - после COMPLETED обычный повторный запуск запрещён;
        - после FAILED новый запуск разрешён;
        - одновременно для одного Blueprint допускается
          максимум один RUNNING;
        - окончательная защита от параллельных RUNNING
          обеспечивается partial UNIQUE index PostgreSQL.

    Service владеет транзакцией.

    AI provider здесь не вызывается.
    """

    # =====================================================
    # START
    # =====================================================

    @classmethod
    async def start(
            cls,
            db: AsyncSession,
            *,
            blueprint_id: int,
            question_count: int,
            created_by_user_id: int | None,
    ) -> int:
        cls._validate_start_input(
            blueprint_id=blueprint_id,
            question_count=question_count,
        )

        try:
            has_completed = (
                await AIQuestionGenerationRunRepo
                .has_completed_for_blueprint(
                    db,
                    blueprint_id=blueprint_id,
                )
            )

            if has_completed:
                raise ValueError(
                    "AI generation for this Blueprint "
                    "has already been completed."
                )

            run = AIQuestionGenerationRun(
                blueprint_id=blueprint_id,
                status=AIQuestionGenerationRunStatus.RUNNING,
                question_count=question_count,
                created_by_user_id=created_by_user_id,
            )

            run = await AIQuestionGenerationRunRepo.create(
                db,
                run=run,
            )

            if run.id is None:
                raise RuntimeError(
                    "AI generation run was not assigned an id."
                )

            run_id = cast(int, run.id)

            await db.commit()

            return run_id

        except IntegrityError as exc:
            await db.rollback()

            raise ValueError(
                "AI generation for this Blueprint "
                "is already running."
            ) from exc

        except Exception:
            await db.rollback()
            raise
    # =====================================================
    # COMPLETE
    # =====================================================

    @classmethod
    async def complete(
            cls,
            db: AsyncSession,
            *,
            run_id: int,
    ) -> None:
        """
        Transaction-owning facade.

        Сохраняет прежний публичный контракт complete().
        """

        try:
            await cls.complete_in_transaction(
                db,
                run_id=run_id,
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    @classmethod
    async def complete_in_transaction(
            cls,
            db: AsyncSession,
            *,
            run_id: int,
    ) -> None:
        """
        RUNNING -> COMPLETED внутри транзакции caller.

        COMMIT / ROLLBACK здесь намеренно отсутствуют.
        """

        cls._validate_run_id(run_id)

        run = await AIQuestionGenerationRunRepo.get_by_id(
            db,
            run_id=run_id,
        )

        if run is None:
            raise ValueError(
                "AI generation run not found."
            )

        cls._require_running(
            run=run,
            operation="complete",
        )

        run.status = (
            AIQuestionGenerationRunStatus.COMPLETED
        )

        run.completed_at = cls._utcnow()
        run.error_code = None

        await AIQuestionGenerationRunRepo.flush(db)
    # =====================================================
    # FAIL
    # =====================================================

    @classmethod
    async def fail(
        cls,
        db: AsyncSession,
        *,
        run_id: int,
        error_code: str | None,
    ) -> None:
        cls._validate_run_id(run_id)

        normalized_error_code = cls._normalize_error_code(
            error_code
        )

        try:
            run = await AIQuestionGenerationRunRepo.get_by_id(
                db,
                run_id=run_id,
            )

            if run is None:
                raise ValueError(
                    "AI generation run not found."
                )

            cls._require_running(
                run=run,
                operation="fail",
            )

            run.status = (
                AIQuestionGenerationRunStatus.FAILED
            )

            run.error_code = normalized_error_code
            run.completed_at = cls._utcnow()

            await AIQuestionGenerationRunRepo.flush(db)

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # =====================================================
    # VALIDATION
    # =====================================================

    @staticmethod
    def _validate_start_input(
        *,
        blueprint_id: int,
        question_count: int,
    ) -> None:
        if blueprint_id <= 0:
            raise ValueError(
                "blueprint_id must be positive."
            )

        if question_count <= 0:
            raise ValueError(
                "question_count must be positive."
            )

    @staticmethod
    def _validate_run_id(
        run_id: int,
    ) -> None:
        if run_id <= 0:
            raise ValueError(
                "run_id must be positive."
            )

    @staticmethod
    def _require_running(
        *,
        run: AIQuestionGenerationRun,
        operation: str,
    ) -> None:
        if (
            run.status
            != AIQuestionGenerationRunStatus.RUNNING
        ):
            raise ValueError(
                "AI generation run must be RUNNING "
                f"to {operation}. "
                f"Current status: {run.status.value}."
            )

    # =====================================================
    # HELPERS
    # =====================================================

    @staticmethod
    def _normalize_error_code(
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalized = value.strip()

        if not normalized:
            return None

        if len(normalized) > 100:
            raise ValueError(
                "error_code must not exceed 100 characters."
            )

        return normalized

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)
