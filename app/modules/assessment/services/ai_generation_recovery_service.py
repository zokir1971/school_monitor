"""Owner-scoped proposal recovery. One transaction saves one reviewed draft pair.

No provider is imported or called. SQL count is bounded independently of set size.
"""
from app.modules.assessment.helpers.generation_recovery import (
    bounded_json, restore_input, slot_editor, update_slot, validate_slot)
from app.modules.assessment.repositories.teacher_ai_question_run_repo import TeacherAIQuestionRunRepo as Repo
from app.modules.assessment.services.teacher_ai_question_web_service import validate_token, AIRequestNotFound
from app.modules.assessment.services.teacher_ai_question_generation_service import TeacherAIQuestionGenerationService as Single
from app.modules.assessment.services.ai_question_generator_service import AIQuestionGeneratorService as Generator
from app.modules.assessment.repositories.learning_objective_table_import_repo import LearningObjectiveTableImportRepo
from app.modules.assessment.services.generated_bilingual_service import save_generated_variants


class RecoveryConflict(ValueError):
    pass


class AIGenerationRecoveryService:
    @staticmethod
    async def import_diagnostic(*, session_factory, token, user_id, staff_member_id,
                                diagnostic_json, quarter, education_track):
        """Explicit upload of an existing diagnostic; never reads arbitrary paths."""
        from app.modules.assessment.helpers.generation_recovery import restore_request, make_proposal
        from app.modules.assessment.schemas.teacher_ai_question_dto import TeacherAIQuestionInputDTO
        from app.modules.assessment.enums import AssessmentQuestionType, AssessmentQuestionDifficulty
        from decimal import Decimal
        validate_token(token)
        diagnostic = bounded_json(diagnostic_json)
        if not isinstance(diagnostic, dict) or diagnostic.get('format') != 'school_monitor_bilingual_v1':
            raise ValueError('Выберите диагностический JSON School Monitor.')
        recorded = restore_request(diagnostic['request'])
        if (len(recorded.objectives) != 1 or not recorded.creation_plan
                or len(recorded.creation_plan) != recorded.question_count or not 1 <= quarter <= 4):
            raise ValueError('В диагностике должен быть один учебный контекст и полный план набора.')
        slot = recorded.creation_plan[0]
        data = TeacherAIQuestionInputDTO(subject_id=recorded.subject_id, grade_level=recorded.grade_level,
            quarter=quarter, objective_id=recorded.objectives[0].learning_objective_id,
            question_type=AssessmentQuestionType(slot['question_type']),
            difficulty=AssessmentQuestionDifficulty(slot['difficulty']), language=recorded.language,
            max_score=Decimal(str(slot['max_score'])), title=recorded.assessment_title,
            education_track=education_track if recorded.grade_level in (10,11) else None,
            creation_plan=tuple(dict(slot, count=1) for slot in recorded.creation_plan))
        async with session_factory() as db:
            try:
                row = await Repo.get(db, token=token, user_id=user_id, lock=True)
                if row is None or row['status'] != 'failed':
                    raise AIRequestNotFound('Неудачный запрос не найден.')
                if row.get('proposal'):
                    raise RecoveryConflict('Ответ уже сохранён. Откройте редактор восстановления.')
                current = await Single.build_request(db, staff_member_id=staff_member_id, data=data)
                proposal = make_proposal(diagnostic['response'], current, data)
                await Repo.save_proposal(db, token=token, user_id=user_id, proposal=proposal)
                await db.commit()
            except BaseException:
                await db.rollback()
                raise

    @staticmethod
    async def view(*, session_factory, token, user_id):
        validate_token(token)
        async with session_factory() as db:
            row = await Repo.get(db, token=token, user_id=user_id)
        if row is None or not row.get('proposal') or row['status'] != 'failed':
            raise AIRequestNotFound('Сохранённый ответ AI не найден.')
        return row

    @staticmethod
    def cards(row):
        proposal = row['proposal']
        cards = []
        # Pure validation only: no per-question SQL or API calls.
        for index in range(len(proposal['raw']['questions'])):
            saved = proposal.get('saved', {}).get(str(index))
            try:
                editor = slot_editor(proposal, index)
                validate_slot(proposal, index)
                error = None
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                error = str(exc)
                try: editor = slot_editor(proposal, index)
                except (ValueError, TypeError, KeyError, IndexError): editor = None
            cards.append(dict(index=index, saved=saved, error=error, editor=editor))
        return cards

    @classmethod
    async def edit(cls, *, session_factory, token, user_id, staff_member_id, index,
                   revision, editor_json, save=False):
        validate_token(token)
        edited = bounded_json(editor_json)
        async with session_factory() as db:
            try:
                row = await Repo.get(db, token=token, user_id=user_id, lock=True)
                if row is None or row['status'] != 'failed' or not row.get('proposal'):
                    raise AIRequestNotFound('Сохранённый ответ AI не найден.')
                proposal = row['proposal']
                # Duplicate save submissions return the existing draft. No new item.
                existing = proposal.get('saved', {}).get(str(index))
                if existing is not None:
                    return existing, None
                if revision != proposal['revision']:
                    raise RecoveryConflict('Ответ изменён в другой вкладке. Обновите страницу перед редактированием.')
                data = restore_input(proposal['input'])
                # Recheck current teaching scope, active objective, quarter and track.
                current_request = await Single.build_request(db, staff_member_id=staff_member_id, data=data)
                updated = update_slot(proposal, index, edited)
                item_id = None
                try:
                    one, response = validate_slot(updated, index, request=current_request)
                    error = None
                except (ValueError, TypeError, KeyError, IndexError) as exc:
                    error = str(exc)
                if save and error is None:
                    result = await Generator.save_generated_questions_in_transaction(
                        db, request=one, response=response, created_by_user_id=user_id)
                    await LearningObjectiveTableImportRepo.assign_item_quarter(
                        db, item_ids=list(result.item_ids), quarter=data.quarter)
                    await save_generated_variants(db, item_ids=list(result.item_ids), response=response,
                        user_id=user_id, language=data.language)
                    item_id = result.item_ids[0]
                    updated['saved'][str(index)] = item_id
                await Repo.save_proposal(db, token=token, user_id=user_id, proposal=updated)
                await db.commit()
                return item_id, error
            except BaseException:
                await db.rollback()
                raise
