# app/modules/assessment/services/blueprint_ai_generation_service.py
from __future__ import annotations

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
)

from app.modules.assessment.ai.question_provider import (
    AIQuestionProvider,
)
from app.modules.assessment.services.ai_question_generation_request_service import (
    AIQuestionGenerationRequestService,
)
from app.modules.assessment.services.ai_question_generation_run_service import (
    AIQuestionGenerationRunService,
)
from app.modules.assessment.services.ai_question_generator_service import (
    AIGeneratedQuestionBankResult,
    AIQuestionGeneratorService,
)


class BlueprintAIGenerationService:
    """
    Orchestration полного AI-generation flow
    для AssessmentBlueprint.

    Граница выполнения:

        1. READ SESSION
           Blueprint -> AIQuestionGenerationRequestDTO

        2. READ SESSION CLOSED

        3. RUN SESSION
           создать AIQuestionGenerationRun(RUNNING)
           COMMIT

        4. RUN SESSION CLOSED
           AI provider -> AIQuestionGenerationResponseDTO

        5. NEW WRITE SESSION
           response -> QuestionBankItem DRAFT
           COMMIT

        6. NEW RUN SESSION
           RUNNING -> COMPLETED
           COMMIT

    При ошибке после успешного start():

        RUNNING -> FAILED

    Внешний AI provider никогда не вызывается
    внутри DB session.
    """

    @classmethod
    async def generate_from_blueprint(
            cls,
            *,
            session_factory: async_sessionmaker[AsyncSession],
            provider: AIQuestionProvider,
            blueprint_id: int,
            created_by_user_id: int | None,
            additional_requirements: str | None = None,
    ) -> AIGeneratedQuestionBankResult:
        if blueprint_id <= 0:
            raise ValueError(
                "blueprint_id must be positive."
            )

        # =====================================================
        # PHASE A — SHORT READ SESSION
        # =====================================================

        async with session_factory() as db:
            request = (
                await AIQuestionGenerationRequestService
                .build_from_blueprint(
                    db,
                    blueprint_id=blueprint_id,
                    additional_requirements=(
                        additional_requirements
                    ),
                )
            )

        # request теперь самостоятельный DTO.
        # ORM session больше не нужна.

        # =====================================================
        # PHASE B — START GENERATION RUN
        # =====================================================

        async with session_factory() as db:
            run_id = (
                await AIQuestionGenerationRunService.start(
                    db,
                    blueprint_id=blueprint_id,
                    question_count=request.question_count,
                    created_by_user_id=(
                        created_by_user_id
                    ),
                )
            )

        # RUNNING уже COMMIT.
        #
        # Поэтому:
        #   - concurrent generation блокируется БД;
        #   - completed generation блокируется service;
        #   - provider вызывается только после guard.

        try:
            # =================================================
            # PHASE C — EXTERNAL AI PROVIDER
            # =================================================

            response = await provider.generate_questions(
                request
            )

            # DB session во время внешнего API вызова отсутствует.

            # =================================================
            # PHASE D — ATOMIC WRITE TRANSACTION
            # =================================================
            #
            # В ОДНОЙ транзакции:
            #
            #   1. QuestionBankItem + objective links
            #   2. RUNNING -> COMPLETED
            #   3. COMMIT
            #
            # Если любой шаг падает:
            #
            #   ROLLBACK всего блока.
            # =================================================

            async with session_factory() as db:
                try:
                    result = (
                        await AIQuestionGeneratorService
                        .save_generated_questions_in_transaction(
                            db,
                            request=request,
                            response=response,
                            created_by_user_id=(
                                created_by_user_id
                            ),
                        )
                    )

                    await (
                        AIQuestionGenerationRunService
                        .complete_in_transaction(
                            db,
                            run_id=run_id,
                        )
                    )

                    await db.commit()

                except Exception:
                    await db.rollback()
                    raise

        except Exception as exc:
            # =================================================
            # FAILURE
            # =================================================
            #
            # Если упал:
            #   - provider;
            #   - validation;
            #   - persistence;
            #   - complete_in_transaction;
            #   - final commit;
            #
            # основной write block уже откатан.
            #
            # Теперь отдельной короткой транзакцией:
            #
            #   RUNNING -> FAILED
            # =================================================

            await cls._mark_run_failed(
                session_factory=session_factory,
                run_id=run_id,
                error_code=cls._get_error_code(exc),
            )

            raise

        return result
    # =========================================================
    # FAILURE HANDLING
    # =========================================================

    @classmethod
    async def _mark_run_failed(
            cls,
            *,
            session_factory: async_sessionmaker[AsyncSession],
            run_id: int,
            error_code: str | None,
    ) -> None:
        """
        Пытается перевести RUNNING -> FAILED.

        Ошибка фиксации FAILED не должна подменять
        исходную ошибку provider / persistence.
        """

        try:
            async with session_factory() as db:
                await AIQuestionGenerationRunService.fail(
                    db,
                    run_id=run_id,
                    error_code=error_code,
                )

        except (ValueError, SQLAlchemyError):
            # Исходное исключение provider / persistence
            # важнее вторичной ошибки lifecycle update.
            #
            # Позже здесь подключим logger.exception().
            pass
    # =========================================================
    # ERROR CODE
    # =========================================================

    @staticmethod
    def _get_error_code(
        exc: Exception,
    ) -> str:
        """
        Получает стабильный короткий error_code.

        AIProviderError уже имеет собственный code.
        Для остальных исключений используем имя класса.
        """

        code = getattr(exc, "code", None)

        if isinstance(code, str):
            normalized = code.strip()

            if normalized:
                return normalized[:100]

        return exc.__class__.__name__[:100]
