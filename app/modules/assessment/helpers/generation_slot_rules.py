"""Explicit per-question generation instructions; the existing validators own policy."""
from decimal import Decimal


def slot_rules(kind, score, params=None):
    from .element_scoring import weighted, parameters
    if params and weighted(params):
        meta=parameters(kind,params)
        result=slot_rules(kind, meta['correct_option_count'] if kind=='multiple_choice' else sum(meta['criterion_points']) if kind=='manual_review' else meta['element_count'])
        result.update(meta,max_score=str(score),scoring='Each correct element earns points_per_element; wrong/missing earns zero. Counts are independent of max_score. Multiple_choice exact set earns full score, otherwise zero. Manual criteria use criterion_points.')
        return result
    score = Decimal(str(score))
    result = {'question_type': kind, 'max_score': str(score)}
    if kind == 'single_choice':
        from .single_choice_score_policy import single_choice_count
        result.update(required_count=single_choice_count(score), counted_field='parts', options_per_part=4, correct_options_per_part=1, scoring='One point per independently answered part; each part owns A-D and exactly one correct option.')
    elif kind == 'image_choice':
        result.update(correct_options=1, options=4,
                      scoring='One correct option earns the entire max_score; score is NOT an option count.')
    elif kind == 'multiple_choice':
        from .multiple_choice_score_policy import multiple_choice_answer_count
        options = 4
        count = multiple_choice_answer_count(score, options)
        result.update(correct_options=count, options=options, incorrect_options=options-count,
                      scoring='Every genuinely true option must be in answer_key.values; never use all-correct options.')
    elif kind in {'true_false', 'number', 'matching', 'ordering', 'fill_gaps', 'formula'}:
        # Import the same count functions used by authoring validators.
        from .number_score_policy import part_count
        from .true_false_score_policy import assertion_count
        from .matching_score_policy import matching_count
        from .ordering_score_policy import ordering_count
        from .formula_score_policy import formula_count
        count = {'true_false': assertion_count, 'matching': matching_count, 'ordering': ordering_count,
                 'formula': formula_count}.get(kind, part_count)(score)
        field = {'true_false': 'statements', 'number': 'parts', 'matching': 'pairs',
                 'ordering': 'items', 'fill_gaps': 'gaps', 'formula': 'parts'}[kind]
        result.update(required_count=count, counted_field=field, scoring='Exactly one point per counted element.')
        if kind == 'matching':
            result.update(left_items=count, right_items=count, one_to_one=True)
    elif kind == 'manual_review':
        result.update(scoring='Positive integer criterion points must sum exactly to max_score; no fractional points.')
    elif kind == 'short_text':
        result.update(scoring='One short response earns the entire max_score; accepted_answers are equivalent spellings, not separate tasks.')
    return result


def generation_plan(request):
    slots = request.creation_plan
    if not slots:
        slots = [dict(question_type=row.question_type.value, max_score=str(row.max_score/row.question_count))
                 for row in request.question_types for _ in range(row.question_count)]
    return [dict(slot_rules(slot['question_type'], slot['max_score'], slot),
                 slot_id=f'Q{index:03d}', difficulty=slot.get('difficulty'),
                 objective_ids=[o.learning_objective_id for o in request.objectives])
            for index, slot in enumerate(slots, 1)]
