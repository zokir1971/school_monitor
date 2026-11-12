# app/modules/assessment/helpers/ai_question_contract.py
"""AI-specific checks, without changing contracts of existing saved questions."""
from app.modules.assessment.helpers.multiple_choice_score_policy import validate_multiple_choice_score
from app.modules.assessment.helpers.true_false_score_policy import validate_true_false
from app.modules.assessment.helpers.number_score_policy import validate_number_parts
from app.modules.assessment.helpers.matching_score_policy import validate_matching_score
from app.modules.assessment.helpers.ordering_score_policy import validate_ordering_score
from app.modules.assessment.helpers.formula_score_policy import validate_formula_parts
from app.modules.assessment.helpers.fill_gaps_score_policy import validate_fill_gaps_score
from decimal import Decimal, InvalidOperation
from .single_choice_score_policy import validate_single_choice_parts
from app.modules.assessment.enums import AssessmentQuestionType, AssessmentQuestionDifficulty
from app.modules.assessment.helpers.manual_review_criteria import validate_manual_criteria
from app.modules.assessment.services.question_bank_media_service import validate_media_segment


def validate_question_score(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError('max_score must be a number.')
    try:
        score = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError('max_score is invalid.') from exc
    if not score.is_finite() or not Decimal('0') < score <= Decimal('99999999.99'):
        raise ValueError('max_score must be positive and finite.')
    if score != score.quantize(Decimal('0.01')):
        raise ValueError('max_score must have at most two decimal places.')
    return score


def normalize_text_segments(text, segments=None, *, allow_images=False):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Question text must not be empty.')
    # Backward compatibility for earlier plain-text generated DTOs.
    if segments is None or isinstance(segments, tuple) and not segments:
        return {'type': 'text', 'text': text.strip()},
    if not isinstance(segments, (list, tuple)) or not segments or len(segments) > 1000:
        raise ValueError('text_segments must contain 1–1000 segments.')
    result = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError('Each text_segments item must be an object.')
        kind = segment.get('type')
        if kind in {'text', 'latex'}:
            value = segment.get('text')
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Each text/latex segment must contain non-empty text.')
            result.append({'type': kind, 'text': value})
        elif kind == 'image' and allow_images:
            validate_media_segment(segment)
            result.append({'type': 'image', 'object_key': segment['object_key'], 'alt': segment.get('alt', '')})
        else:
            raise ValueError('AI generation supports text/latex segments; uploaded media requires a separate asset '
                             'workflow.')
    return tuple(result)


def segments_plain_text(segments):
    return ''.join('[Сурет]' if s['type'] == 'image' else s['text'] for s in segments).strip()


def validate_review_contract(*, question_type, grading_settings, max_score):
    score = validate_question_score(max_score)
    if question_type == AssessmentQuestionType.MANUAL_REVIEW:
        validate_manual_criteria(grading_settings.get('criteria'), max_score=score)


def validate_generated_question(question):
    from .element_scoring import weighted, validate_elements, clean_grading
    if weighted(question.grading_settings):
        from dataclasses import replace
        score=validate_elements(question.question_type.value,question.content,question.answer_key,question.grading_settings,question.max_score)
        return validate_generated_question(replace(question,max_score=Decimal(score),grading_settings=clean_grading(question.grading_settings)))
    if not isinstance(question.question_type, AssessmentQuestionType) or not isinstance(question.difficulty,
                                                                                        AssessmentQuestionDifficulty):
        raise ValueError('AI question type and difficulty must be enum values.')
    for name in ('title', 'instruction', 'explanation'):
        value = getattr(question, name)
        if value is not None and not isinstance(value, str):
            raise ValueError(f'AI {name} must be a string or None.')
    ids = question.learning_objective_ids
    if not isinstance(ids, tuple) or any(isinstance(i, bool) or not isinstance(i, int) or i <= 0 for i in ids) or len(
            ids) != len(set(ids)):
        raise ValueError('AI learning_objective_ids must contain unique positive integers.')
    normalize_text_segments(question.text, question.text_segments, allow_images=True)
    validate_review_contract(question_type=question.question_type,
                             grading_settings=question.grading_settings, max_score=question.max_score)
    kind = question.question_type
    if kind == AssessmentQuestionType.IMAGE_CHOICE:
        from app.modules.assessment.services.assessment_question_validation_service import AssessmentQuestionValidationService
        AssessmentQuestionValidationService.validate(question_type=kind, content=question.content,
            answer_key=question.answer_key, grading_settings=question.grading_settings)
        options = question.content.get('options', [])
        if len(options) != 4 or [option.get('value') for option in options] != list('ABCD'):
            raise ValueError('IMAGE_CHOICE requires four images A–D.')
    if kind == AssessmentQuestionType.SINGLE_CHOICE:
        validate_single_choice_parts(question.content, question.answer_key, question.grading_settings,
            max_score=question.max_score, require_parts=question.max_score > 1, allow_images=False)
    if kind == AssessmentQuestionType.MULTIPLE_CHOICE or (kind == AssessmentQuestionType.SINGLE_CHOICE and 'parts' not in question.content):
        options = question.content.get('options', [])
        if len(options) != 4 or [o.get('value') for o in options] != list('ABCD'):
            raise ValueError('AI choice questions require four options A–D in order for the shared editor.')
    if kind == AssessmentQuestionType.MULTIPLE_CHOICE:
        validate_multiple_choice_score(content=question.content, answer_key=question.answer_key,
                                       max_score=question.max_score)
    if kind == AssessmentQuestionType.TRUE_FALSE:
        validate_true_false(question.content, question.answer_key, max_score=question.max_score,
                            require_statements=True, allow_images=False)
    if kind == AssessmentQuestionType.NUMBER:
        validate_number_parts(question.content, question.answer_key, question.grading_settings,
                              max_score=question.max_score, require_parts=True, allow_images=False)
    if kind == AssessmentQuestionType.MATCHING:
        validate_matching_score(question.content, question.answer_key, question.grading_settings,
                                max_score=question.max_score, require_policy=True, allow_images=False)
    if kind == AssessmentQuestionType.ORDERING:
        validate_ordering_score(question.content, question.answer_key, question.grading_settings,
                                max_score=question.max_score, require_policy=True, allow_images=False)
    if kind == AssessmentQuestionType.FORMULA:
        if question.grading_settings.get('variable_meanings_required') is not True:
            raise ValueError('AI FORMULA must include variable meanings.')
        validate_formula_parts(question.content, question.answer_key, question.grading_settings,
                               max_score=question.max_score, require_parts=True)
    if kind == AssessmentQuestionType.FILL_GAPS:
        validate_fill_gaps_score(question.content, question.answer_key, question.grading_settings,
                                max_score=question.max_score, require_policy=True)
        for gap in question.answer_key['gaps'].values():
            if any('[[' in answer or ']]' in answer for answer in gap['accepted_answers']):
                raise ValueError('Gap answers cannot contain editor delimiters [[ or ]].')
