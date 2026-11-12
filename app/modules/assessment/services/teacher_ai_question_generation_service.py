"""One AI_GENERATED / DRAFT for a teacher; no Blueprint or HTTP dependency."""
from __future__ import annotations
from dataclasses import replace
from app.modules.assessment.helpers.question_creation_plan import parse_plan, apply_plan, validate_plan_response

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.modules.assessment.helpers.ai_education_track import selected_track, validate_objective_track
from app.modules.assessment.ai.question_provider import AIQuestionProvider
from app.modules.assessment.enums import AssessmentLanguage, AssessmentQuestionDifficulty, AssessmentQuestionType
from app.modules.assessment.helpers.ai_question_contract import validate_question_score
from app.modules.assessment.ai.question_prompt_builder import AIQuestionPromptBuilder
from app.modules.assessment.repositories.teacher_question_bank_repo import TeacherQuestionBankRepo
from app.modules.assessment.repositories.question_bank_repo import QuestionBankRepo
from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIQuestionGenerationRequestDTO, AIQuestionGenerationObjectiveDTO,
    AIQuestionGenerationTypeDTO, AIQuestionGenerationDifficultyDTO,
)
from app.modules.assessment.schemas.teacher_ai_question_dto import TeacherAIQuestionInputDTO
from app.modules.assessment.services.ai_question_generator_service import AIQuestionGeneratorService, AIGeneratedQuestionBankResult
from app.modules.assessment.repositories.learning_objective_table_import_repo import LearningObjectiveTableImportRepo
from app.modules.assessment.services.generated_bilingual_service import save_generated_variants



def positive_integer(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f'{name} must be a positive integer.')


class TeacherAIQuestionGenerationService:
    @staticmethod
    async def build_request(db: AsyncSession, *, staff_member_id: int, data: TeacherAIQuestionInputDTO) -> AIQuestionGenerationRequestDTO:
        positive_integer(staff_member_id, 'staff_member_id')
        for name in ('subject_id', 'grade_level', 'quarter', 'objective_id'):
            positive_integer(getattr(data, name), name)
        if not 1 <= data.grade_level <= 12 or not 1 <= data.quarter <= 4:
            raise ValueError('Grade must be 1–12; quarter must be 1–4.')
        for name, enum_class in [('question_type', AssessmentQuestionType),
                                 ('difficulty', AssessmentQuestionDifficulty), ('language', AssessmentLanguage)]:
            if not isinstance(getattr(data, name), enum_class):
                raise ValueError(f'{name} must be the corresponding enum.')
        selected_track(data.grade_level, data.education_track)
        score = validate_question_score(data.max_score)
        if data.image_option_keys:
            from app.modules.assessment.services.question_bank_media_service import MEDIA_KEY_PATTERN
            if len(data.image_option_keys) != 4 or len(set(data.image_option_keys)) != 4 or any(not MEDIA_KEY_PATTERN.fullmatch(k) for k in data.image_option_keys):
                raise ValueError('Нужны четыре разных изображения A–D / Төрт түрлі A–D суреті қажет.')
        if data.question_type == AssessmentQuestionType.IMAGE_CHOICE and len(data.image_option_keys) != 4:
            raise ValueError('Загрузите варианты A–D / A–D нұсқаларын жүктеңіз.')
        for name, limit in [('title', 255), ('additional_requirements', 10000)]:
            value = getattr(data, name)
            if value is not None and (not isinstance(value, str) or len(value) > limit):
                raise ValueError(f'{name} must be a string of at most {limit} characters.')
        scope = await TeacherQuestionBankRepo.list_teaching_scope(db, staff_member_id=staff_member_id)
        selected = next((row for row in scope if row.subject_id == data.subject_id and row.grade_level == data.grade_level), None)
        if selected is None:
            raise ValueError('Subject and grade are outside the teacher teaching scope.')
        objectives = await QuestionBankRepo.get_learning_objectives_by_ids(db, learning_objective_ids=[data.objective_id])
        if len(objectives) != 1:
            raise ValueError('Learning objective was not found.')
        objective = objectives[0]
        validate_objective_track(getattr(objective, 'education_track', ''), data.grade_level, data.education_track)
        eligible_ids = await LearningObjectiveTableImportRepo.objective_ids_in_quarter(db, objective_ids=[data.objective_id], quarter=data.quarter)
        if (not objective.is_active or objective.subject_id != data.subject_id or
                objective.grade_level != data.grade_level or objective.id not in eligible_ids):
            raise ValueError('Learning objective must be active and match subject, grade and quarter.')
        russian = data.language == AssessmentLanguage.RUSSIAN
        objective_text = (objective.title_ru or objective.title_kz) if russian else (objective.title_kz or objective.title_ru)
        language = 'ru' if russian else 'kz'
        formulation_text = await LearningObjectiveTableImportRepo.formulation_text(db, objective_id=objective.id, quarter=data.quarter, language=language)
        if formulation_text == '':
            formulation_text = await LearningObjectiveTableImportRepo.formulation_text(db, objective_id=objective.id, quarter=data.quarter, language='kz' if russian else 'ru')
        if formulation_text is not None:
            objective_text = formulation_text

        subject_name = (selected.subject_name_ru or selected.subject_name_kz) if russian else selected.subject_name_kz
        if not isinstance(objective_text, str) or not objective_text.strip():
            raise ValueError('Learning objective text is empty.')
        difficulty = {level.value: 100 if level == data.difficulty else 0 for level in AssessmentQuestionDifficulty}
        request = AIQuestionGenerationRequestDTO(
            blueprint_id=None, subject_id=data.subject_id, subject_name=subject_name,
            grade_level=data.grade_level, language=data.language,
            assessment_title=(data.title or '').strip() or f'{objective.code} — {subject_name}'[:255],
            question_count=1, max_score=score,
            objectives=(AIQuestionGenerationObjectiveDTO(data.objective_id, objective.code, objective_text.strip(), 1, score),),
            question_types=(AIQuestionGenerationTypeDTO(data.question_type, 1, score),),
            difficulty=AIQuestionGenerationDifficultyDTO(**difficulty),
            additional_requirements=((data.additional_requirements or '').strip() + ('\nEducation track: '+data.education_track if data.grade_level in (10,11) else '') + ('\nЕсли цель содержит несколько формулировок, выбери одну из них для задания. Не смешивай жанры разных формулировок и не изменяй их смысл.' if formulation_text is not None else '')).strip() or None,
        )
        if data.creation_plan:
            request = apply_plan(request, parse_plan(data.creation_plan, ai=True))
        request = replace(request, image_option_keys=data.image_option_keys)
        AIQuestionPromptBuilder.build(request)  # Reject invalid input before a paid provider call.
        return replace(request, source_image_key=data.source_image_key)

    @classmethod
    async def generate_and_save(cls, *, session_factory: async_sessionmaker[AsyncSession], provider: AIQuestionProvider, user_id: int,
                                staff_member_id: int, data: TeacherAIQuestionInputDTO) -> AIGeneratedQuestionBankResult:
        """Caller supplies authenticated user/staff IDs; provider runs outside DB sessions.

        Returns AIGeneratedQuestionBankResult with exactly one draft ID.
        UI routes and a durable duplicate-request/run guard are added in the next stage.
        """
        positive_integer(user_id, 'user_id')
        async with session_factory() as db:
            request = await cls.build_request(db, staff_member_id=staff_member_id, data=data)
        response = await provider.generate_questions(request)
        validate_plan_response(request, response)
        if not data.creation_plan and (len(response.questions) != 1 or response.questions[0].difficulty != data.difficulty):
            raise ValueError('Single generation must return one question of the requested difficulty.')
        async with session_factory() as db:
            try:
                # Recheck teaching scope and objective after the potentially long provider call.
                await cls.build_request(db, staff_member_id=staff_member_id, data=data)
                result = await AIQuestionGeneratorService.save_generated_questions_in_transaction(
                    db, request=request, response=response, created_by_user_id=user_id,
                )
                await LearningObjectiveTableImportRepo.assign_item_quarter(db, item_ids=list(result.item_ids), quarter=data.quarter)
                await save_generated_variants(db, item_ids=list(result.item_ids), response=response,
                    user_id=user_id, language=data.language)
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise

