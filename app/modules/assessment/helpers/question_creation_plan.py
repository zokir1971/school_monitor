"""Pure shared plan validation: count is separate from score per question."""
import json
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from app.modules.assessment.enums import AssessmentQuestionType, AssessmentQuestionDifficulty
from app.modules.assessment.schemas.ai_question_generator_dto import AIQuestionGenerationTypeDTO
from .element_scoring import POLICY, COUNTED, parameters, maximum, weighted

MAX_QUESTIONS = 10


def parse_plan(raw, *, ai=False):
    try:
        if isinstance(raw, str) and len(raw) > 20000:
            raise ValueError()
        rows = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= MAX_QUESTIONS:
            raise ValueError('Количество строк: 1–10 / Жол саны: 1–10.')
        result = []
        for row_index, row in enumerate(rows, 1):
            kind = AssessmentQuestionType(row['question_type']).value
            level = AssessmentQuestionDifficulty(row['difficulty']).value
            count = row['count']
            if type(count) is not int or not 1 <= count <= MAX_QUESTIONS:
                raise ValueError('Количество карточек: целое число 1–10 / Карточкалар саны: 1–10 бүтін сан.')
            if row.get('element_score_policy') == POLICY:
                meta = parameters(kind, row)
                result.append(
                    dict(question_type=kind, difficulty=level, count=count, max_score=str(maximum(meta)), **meta))
                continue
            score = Decimal(str(row['max_score']))
            if not score.is_finite() or score <= 0 or score > 100 or score.as_tuple().exponent < -2:
                raise ValueError()
            if kind in {'single_choice', 'multiple_choice', 'true_false', 'number', 'matching', 'ordering', 'fill_gaps',
                        'formula', 'manual_review'}:
                if score != score.to_integral_value() or score < (
                        2 if kind in {'multiple_choice', 'matching', 'ordering'} else 1):
                    raise ValueError()
            if ai and kind == 'multiple_choice' and score not in (2, 3):
                raise ValueError()
            result.append(dict(question_type=kind, difficulty=level, count=count, max_score=str(score)))
        if sum(r['count'] for r in result) > MAX_QUESTIONS:
            raise ValueError('Всего не более 10 карточек / Барлығы 10 карточкадан аспауы керек.')
        if ai:
            elements = sum(r['count'] * r.get('element_count',
                                              int(Decimal(r['max_score'])) if r['question_type'] in COUNTED else 1) for
                           r in result)
            if elements > 32:
                raise ValueError(
                    'AI: максимум 32 элемента в одном запросе / Бір сұрауда ең көбі 32 элемент.')
        return tuple(result)
    except (ValueError, TypeError, KeyError, InvalidOperation, OverflowError) as exc:
        failed_row = locals().get("row_index", 1)
        reason = str(exc) or "Проверьте параметры / Параметрлерді тексеріңіз"
        raise ValueError(f"Строка / Жол {failed_row}: {reason}") from exc


def expand_plan(rows):
    return tuple({k: v for k, v in r.items() if k != 'count'}
                 for r in rows for _ in range(r['count']))


def apply_plan(request, rows):
    slots = expand_plan(rows)
    total = sum((Decimal(s['max_score']) for s in slots), Decimal(0))
    types = {}
    for slot in slots:
        key = AssessmentQuestionType(slot['question_type'])
        count, score = types.get(key, (0, Decimal(0)))
        types[key] = count + 1, score + Decimal(slot['max_score'])
    return replace(request, question_count=len(slots), max_score=total,
                   objectives=(replace(request.objectives[0], question_count=len(slots), max_score=total),),
                   question_types=tuple(
                       AIQuestionGenerationTypeDTO(kind, count, score) for kind, (count, score) in types.items()),
                   difficulty=None, creation_plan=slots)


def validate_plan_response(request, response):
    slots = getattr(request, 'creation_plan', ())
    if not slots:
        return
    if len(response.questions) != len(slots):
        raise ValueError('AI вернул неверное количество заданий набора.')
    objective_id = request.objectives[0].learning_objective_id
    for question, slot in zip(response.questions, slots):
        if weighted(slot):
            if any(question.grading_settings.get(k) != v for k, v in parameters(slot['question_type'], slot).items()):
                raise ValueError('AI изменил параметры оценивания / AI бағалау параметрлерін өзгертті.')
        if (question.question_type.value != slot['question_type'] or question.difficulty.value != slot['difficulty']
                or question.max_score != Decimal(slot['max_score']) or tuple(question.learning_objective_ids) != (
                        objective_id,)):
            raise ValueError('AI изменил тип, уровень, балл или учебную цель задания набора.')
