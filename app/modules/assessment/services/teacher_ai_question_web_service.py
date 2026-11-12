"""Durable idempotency for the web workflow, independently of Blueprint."""
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.modules.assessment.helpers.ai_question_contract import validate_question_score
from app.modules.assessment.repositories.teacher_ai_question_run_repo import TeacherAIQuestionRunRepo as Repo
from app.modules.assessment.services.teacher_ai_question_generation_service import (
    TeacherAIQuestionGenerationService as Single,
)
from app.modules.assessment.services.ai_question_generator_service import AIQuestionGeneratorService as Generator
from app.modules.assessment.repositories.learning_objective_table_import_repo import LearningObjectiveTableImportRepo
from app.modules.assessment.services.generated_bilingual_service import save_generated_variants


logger = logging.getLogger(__name__)


class AIRequestNotFound(ValueError):
    pass


def fingerprint(data):
    values = asdict(data)
    values['max_score'] = str(validate_question_score(data.max_score).normalize())
    for key in ('title', 'additional_requirements'):
        values[key] = (values[key] or '').strip()
    return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def validate_token(token):
    if not isinstance(token, str) or not re.fullmatch(r'[0-9a-f]{32}', token):
        raise AIRequestNotFound('AI сұрауы табылмады.')


class TeacherAIQuestionWebService:
    @staticmethod
    async def issue(*, session_factory, user_id):
        token = uuid4().hex
        async with session_factory() as db:
            try:
                await Repo.create(db, token=token, user_id=user_id)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return token

    @staticmethod
    async def status(*, session_factory, token, user_id):
        validate_token(token)
        async with session_factory() as db:
            row = await Repo.get(db, token=token, user_id=user_id)
        if row is None:
            raise AIRequestNotFound('AI сұрауы табылмады.')
        return row

    @classmethod
    async def generate(cls, *, session_factory, provider, token, user_id, staff_member_id, data):
        validate_token(token)
        digest = fingerprint(data)
        # Row lock serializes POSTs across processes. Only its first claimant calls AI.
        async with session_factory() as db:
            try:
                row = await Repo.get(db, token=token, user_id=user_id, lock=True)
                if row is None:
                    raise AIRequestNotFound('AI сұрауы табылмады.')
                if row['status'] != 'pending':
                    if row['fingerprint'] != digest:
                        raise ValueError('Бұл сұраудың параметрлері өзгерген. Жаңа сұрау жасаңыз.')
                    return row
                if datetime.now(timezone.utc) - row['created_at'] > timedelta(hours=1):
                    raise ValueError('Сұрау мерзімі аяқталған. Бетті жаңартыңыз.')
                request = await Single.build_request(db, staff_member_id=staff_member_id, data=data)
                await Repo.claim(db, token=token, user_id=user_id, fingerprint=digest)
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        response = None
        try:
            response = await provider.generate_questions(request)
            from app.modules.assessment.helpers.question_creation_plan import validate_plan_response
            validate_plan_response(request, response)
            if not getattr(data, 'creation_plan', ()) and (len(response.questions) != 1 or response.questions[0].difficulty != data.difficulty):
                raise ValueError('AI must return one question of the requested difficulty.')
            # Validate before changing option positions; no extra API or SQL calls.
            from app.modules.assessment.ai.question_validation_pipeline import AIQuestionValidationPipeline
            AIQuestionValidationPipeline.validate(response)
            from app.modules.assessment.helpers.generated_option_shuffle import shuffle_generated_options
            response = shuffle_generated_options(response)
            async with session_factory() as db:
                try:
                    row = await Repo.get(db, token=token, user_id=user_id, lock=True)
                    if row is None or row['status'] != 'running':
                        raise ValueError('AI request state is invalid.')
                    await Single.build_request(db, staff_member_id=staff_member_id, data=data)
                    result = await Generator.save_generated_questions_in_transaction(
                        db, request=request, response=response, created_by_user_id=user_id,
                    )
                    await LearningObjectiveTableImportRepo.assign_item_quarter(db, item_ids=list(result.item_ids), quarter=data.quarter)
                    await save_generated_variants(db, item_ids=list(result.item_ids), response=response,
                        user_id=user_id, language=data.language)
                    await Repo.complete(db, token=token, user_id=user_id,
                                        item_id=result.item_ids[0], warnings=result.warnings, item_ids=list(result.item_ids))
                    await db.commit()
                except BaseException:
                    await db.rollback()
                    raise
        except (Exception, asyncio.CancelledError) as exc:
            # Conditional update protects an already committed completed request.
            try:
                async with session_factory() as db:
                    from app.modules.assessment.helpers.generation_recovery import candidate_from_error, make_proposal
                    raw = candidate_from_error(exc) or getattr(provider, 'last_generation_output', None)
                    if raw is not None:
                        try:
                            proposal = make_proposal(raw, request, data)
                        except (ValueError, TypeError, KeyError, RecursionError):
                            proposal = None
                        if proposal is not None:
                            await Repo.save_proposal(db, token=token, user_id=user_id, proposal=proposal)
                    await Repo.fail(db, token=token, user_id=user_id,
                                    error_code=str(getattr(exc, 'code', type(exc).__name__)))
                    await db.commit()
            except Exception:
                logger.exception('Could not mark teacher AI request failed')
            if isinstance(exc, asyncio.CancelledError):
                raise
            logger.exception('Teacher AI request failed; token=%s', token)
        return await cls.status(session_factory=session_factory, token=token, user_id=user_id)

