"""Versioned authoring parameters. Old records have no marker and keep v1 semantics."""
from decimal import Decimal, InvalidOperation
from copy import deepcopy
from dataclasses import replace

POLICY = 'weighted_elements_v2'
SINGLE = {'short_text', 'multiple_choice', 'image_choice'}
COUNTED = {'single_choice', 'true_false', 'number', 'matching', 'ordering', 'fill_gaps', 'formula'}

def integer(value, minimum=1, maximum=100):
    if isinstance(value, bool):raise ValueError('Укажите целое число / Бүтін сан енгізіңіз.')
    try:number=Decimal(str(value))
    except (InvalidOperation, ValueError):raise ValueError('Укажите целое число / Бүтін сан енгізіңіз.') from None
    if not number.is_finite() or number != number.to_integral_value() or not minimum <= number <= maximum:
        raise ValueError(f'Допустимое целое число: {minimum}–{maximum} / Рұқсат етілген бүтін сан: {minimum}–{maximum}.')
    return int(number)

def parameter_rules():
    kinds=COUNTED | SINGLE | {'manual_review'}
    return {kind:dict(min_elements=2 if kind in {'matching','ordering'} else 1,
                     max_elements=1 if kind in SINGLE else 50 if kind=='manual_review' else 100,
                     max_points=100, correct_min=2, correct_max=3, options=4 if kind in {'single_choice','multiple_choice','image_choice'} else None)
            for kind in sorted(kinds)}

def parameters(kind, values):
    if kind not in parameter_rules():raise ValueError('Неизвестный тип задания / Тапсырма түрі белгісіз.')
    rule=parameter_rules()[kind]
    def field_integer(name, label, minimum=1, maximum=100):
        try:
            return integer(values.get(name), minimum, maximum)
        except ValueError as exc:
            raise ValueError(label + ': ' + str(exc)) from exc
    n=field_integer('element_count', 'Элементов в карточке / Карточкадағы элементтер', rule['min_elements'], rule['max_elements'])
    p=field_integer('points_per_element', 'Баллов за элемент / Элемент балы')
    result=dict(element_score_policy=POLICY,element_count=n,points_per_element=p)
    if kind=='multiple_choice':
        if 'option_count' in values and integer(values['option_count'])!=4:raise ValueError('Поддерживаются 4 варианта / 4 нұсқа қолданылады.')
        result.update(option_count=4,correct_option_count=field_integer('correct_option_count', 'Правильных вариантов / Дұрыс нұсқалар', 2, 3))
    if kind=='manual_review':
        points=values.get('criterion_points')
        if isinstance(points,str):points=[v.strip() for v in points.split(',')]
        if not isinstance(points,(list,tuple)) or len(points)!=n:raise ValueError('Укажите баллы каждого критерия / Әр критерийдің балын көрсетіңіз.')
        result['criterion_points']=[integer(v) for v in points]
    return result

def maximum(meta):
    return sum(meta['criterion_points']) if 'criterion_points' in meta else meta['element_count']*meta['points_per_element']

def weighted(grading):return isinstance(grading,dict) and grading.get('element_score_policy')==POLICY

def policy_score(kind, grading, max_score):
    if not weighted(grading):return max_score
    meta=parameters(kind,grading)
    if Decimal(str(max_score))!=maximum(meta):raise ValueError('Максимальный балл не совпадает с расчётом / Ең жоғары балл есепке сәйкес емес.')
    return maximum(meta) if kind=='manual_review' else meta['correct_option_count'] if kind=='multiple_choice' else meta['element_count']

def clean_grading(grading):
    return {k:deepcopy(v) for k,v in grading.items() if k not in {'element_score_policy','element_count','points_per_element','correct_option_count','option_count','criterion_points'}}

def validate_elements(kind, content, key, grading, max_score):
    score=policy_score(kind,grading,max_score)
    if not weighted(grading):return score
    meta=parameters(kind,grading)
    if kind in COUNTED and grading.get('partial_credit',True) is not True:raise ValueError('Каждый элемент оценивается отдельно / Әр элемент жеке бағаланады.')
    if kind=='multiple_choice' and grading.get('partial_credit',False) is not False:raise ValueError('Нужен точный набор ответов / Жауаптар жиынтығы толық сәйкес болуы керек.')
    for name in ('criterion_points','option_count','correct_option_count'):
        if name in grading and name not in meta:raise ValueError('Параметр не относится к типу задания: '+name)
    if kind in {'single_choice','number','formula'}:
        if len(content.get('parts',[]))!=meta['element_count']:raise ValueError('Количество заданий не совпадает с параметрами / Тапсырмалар саны параметрлерге сәйкес емес.')
    if kind=='true_false' and len(content.get('statements',[]))!=meta['element_count']:raise ValueError('Количество утверждений не совпадает с параметрами.')
    if kind in {'matching','ordering','fill_gaps'}:
        count=len(key.get('pairs',[])) if kind=='matching' else len(content.get('items',[])) if kind=='ordering' else sum(segment.get('type')=='gap' for segment in content.get('segments',[]))
        if count!=meta['element_count']:raise ValueError('Количество элементов не совпадает с параметрами / Элементтер саны параметрлерге сәйкес емес.')
        expected={'matching':'per_pair_v1','ordering':'per_position_v1','fill_gaps':'per_gap_v1'}[kind]
        if grading.get(kind+'_score_policy')!=expected:raise ValueError('Отсутствует политика оценивания элементов: '+kind)
    if kind=='manual_review':
        actual=[int(v['max_score']) for v in grading.get('criteria',[]) if Decimal(str(v.get('max_score',0)))==int(v.get('max_score',0))]
        if actual!=meta['criterion_points']:raise ValueError('Баллы критериев не совпадают с параметрами / Критерий балдары параметрлерге сәйкес емес.')
    return score

def inject_parameters(raw, request):
    slots=getattr(request,'creation_plan',())
    for question,slot in zip(raw.get('questions',[]),slots):
        if not isinstance(question,dict) or not weighted(slot):continue
        meta=parameters(slot['question_type'],slot)
        grading=question.get('grading_settings')
        if not isinstance(grading,dict):raise ValueError('grading_settings must be an object.')
        for name,value in meta.items():
            if name in grading and grading[name]!=value:raise ValueError('AI changed requested scoring parameters: '+name)
        kind=slot['question_type']
        if kind in COUNTED:
            if grading.get('partial_credit',True) is not True:raise ValueError('AI changed partial_credit.')
            grading={**grading,'partial_credit':True}
        if kind=='multiple_choice':
            if grading.get('partial_credit',False) is not False:raise ValueError('AI changed exact-set grading.')
            grading={**grading,'partial_credit':False}
        question['grading_settings']={**grading,**meta}
    return raw

def unit_request(request):
    """Validate old allocation invariants in unit space, without changing the sent request."""
    from .question_creation_plan import apply_plan
    rows=[]
    for slot in request.creation_plan:
        score=policy_score(slot['question_type'],slot,slot['max_score'])
        rows.append(dict(question_type=slot['question_type'],difficulty=slot['difficulty'],count=1,max_score=str(score)))
    return apply_plan(request,rows)

def form_parameters(item=None,slot=None):
    if slot and weighted(slot):return parameters(slot['question_type'],slot)
    if item is not None:
        grading=item.get('grading_settings',{}) if isinstance(item,dict) else getattr(item,'grading_settings',{})
        kind=item.get('question_type') if isinstance(item,dict) else item.question_type
        return parameters(getattr(kind,'value',kind),grading) if weighted(grading) else None
    return parameters('single_choice',dict(element_count=1,points_per_element=1))
