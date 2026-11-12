"""Pure, bounded proposal editing and isolated validation. Never invokes AI/SQL."""
import json
from copy import deepcopy
from dataclasses import asdict, replace
from decimal import Decimal
from app.modules.assessment.enums import AssessmentLanguage, AssessmentQuestionType, AssessmentQuestionDifficulty
from app.modules.assessment.schemas.ai_question_generator_dto import (
    AIQuestionGenerationRequestDTO, AIQuestionGenerationObjectiveDTO,
    AIQuestionGenerationTypeDTO, AIQuestionGenerationDifficultyDTO)
from app.modules.assessment.schemas.teacher_ai_question_dto import TeacherAIQuestionInputDTO
from .bilingual_inline_response import expand_inline_response

MAX_BYTES = 2_000_000


def restore_request(data):
    values = dict(data)
    values['language'] = AssessmentLanguage(values['language'])
    values['max_score'] = Decimal(values['max_score'])
    values['objectives'] = tuple(AIQuestionGenerationObjectiveDTO(**dict(row, max_score=Decimal(row['max_score']))) for row in values['objectives'])
    values['question_types'] = tuple(AIQuestionGenerationTypeDTO(**dict(row, question_type=AssessmentQuestionType(row['question_type']), max_score=Decimal(row['max_score']))) for row in values['question_types'])
    values['difficulty'] = AIQuestionGenerationDifficultyDTO(**values['difficulty']) if values.get('difficulty') else None
    values['creation_plan'] = tuple(values.get('creation_plan') or ())
    return AIQuestionGenerationRequestDTO(**values)


def restore_input(values):
    return TeacherAIQuestionInputDTO(**dict(values,
        language=AssessmentLanguage(values['language']),
        question_type=AssessmentQuestionType(values['question_type']),
        difficulty=AssessmentQuestionDifficulty(values['difficulty']),
        max_score=Decimal(values['max_score']), creation_plan=tuple(values.get('creation_plan') or ())))


def bounded_json(raw):
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > MAX_BYTES:
        raise ValueError('Ответ слишком большой для редактора восстановления.')
    try:
        result = json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise ValueError('Ответ не содержит читаемый JSON.') from exc
    # Enforce depth/node bounds before rendering untrusted generated data.
    remaining = [30000]
    def check(value, depth=0):
        remaining[0] -= 1
        if depth > 30 or remaining[0] < 0:
            raise ValueError('Слишком сложная структура ответа.')
        if isinstance(value, dict):
            for child in value.values(): check(child, depth+1)
        elif isinstance(value, list):
            for child in value: check(child, depth+1)
    check(result)
    return result


def make_proposal(raw, request, data):
    if request.language.value not in ('ru','kk'):
        raise ValueError('Восстановление рассчитано на двуязычные задания RU/KZ.')
    parsed = expand_inline_response(bounded_json(raw))
    questions = parsed.get('questions')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 10:
        raise ValueError('В ответе нет набора заданий для восстановления.')
    return json.loads(json.dumps(dict(version=1, raw=parsed, request=asdict(request),
        input=asdict(data), saved={}, revision=0), ensure_ascii=False, default=str))


def isolated(proposal, index, edited=None, request=None):
    request = request or restore_request(proposal['request'])
    if type(index) is not int or index < 0 or index >= request.question_count:
        raise ValueError('Задание отсутствует в исходном плане.')
    raw = proposal['raw']
    question = deepcopy(raw['questions'][index])
    translation = raw['translation']
    key = 'text_maps' if 'text_maps' in translation else 'questions'
    other = deepcopy(translation[key][index])
    if edited is not None:
        if not isinstance(edited, dict) or set(edited) != {'source', 'translation'}:
            raise ValueError('Редактор должен содержать исходное задание и перевод.')
        question, other = deepcopy(edited['source']), deepcopy(edited['translation'])
    slot = request.creation_plan[index] if request.creation_plan else dict(
        question_type=request.question_types[0].question_type.value,
        max_score=str(request.max_score), difficulty=proposal['input']['difficulty'])
    score = Decimal(str(slot['max_score']))
    one = replace(request, question_count=1, max_score=score,
        objectives=tuple(replace(o, question_count=1, max_score=score) for o in request.objectives),
        question_types=(AIQuestionGenerationTypeDTO(AssessmentQuestionType(slot['question_type']), 1, score),),
        creation_plan=(dict(slot),))
    return one, dict(questions=[question], translation=dict(language=translation['language'], **{key: [other]}))


def validate_slot(proposal, index, edited=None, request=None):
    from app.modules.assessment.ai.bilingual_generation_provider import parse_bilingual
    from app.modules.assessment.ai.question_validation_pipeline import AIQuestionValidationPipeline
    one, raw = isolated(proposal, index, edited, request)
    response = parse_bilingual(json.dumps(raw, ensure_ascii=False), one)
    AIQuestionValidationPipeline.validate(response)
    return one, response


def slot_editor(proposal, index):
    _, raw = isolated(proposal, index)
    key = 'text_maps' if 'text_maps' in raw['translation'] else 'questions'
    source, other = raw['questions'][0], raw['translation'][key][0]
    # Add empty controls for missing allowed text-map fields, without repairing
    # or discarding an invalid translation supplied by the model.
    if key == 'text_maps' and isinstance(other, dict):
        from .bilingual_generation_text_map import text_map_fields
        try:
            kind = AssessmentQuestionType(source['question_type'])
            for address, (_, original) in text_map_fields(source, kind).items():
                if original.strip(): other.setdefault(address, '')
        except (ValueError, KeyError, TypeError):
            pass
    return {'source': source, 'translation': other}


def update_slot(proposal, index, edited):
    updated = deepcopy(proposal)
    _, raw = isolated(proposal, index, edited)
    key = 'text_maps' if 'text_maps' in raw['translation'] else 'questions'
    updated['raw']['questions'][index] = raw['questions'][0]
    updated['raw']['translation'][key][index] = raw['translation'][key][0]
    updated['revision'] += 1
    return updated


def candidate_from_error(error):
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        raw = getattr(error, 'generation_candidate', None)
        if isinstance(raw, str): return raw
        error = error.__cause__ or error.__context__
    return None
