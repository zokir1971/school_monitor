"""Pure parameter and variant rules shared by web, services and future assignment."""
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal

class WorkPlanError(ValueError):
    pass

def integer(value, minimum, maximum):
    try:
        if isinstance(value, bool): raise ValueError
        result = int(str(value))
        if not minimum <= result <= maximum: raise ValueError
        return result
    except (TypeError, ValueError) as exc:
        raise WorkPlanError('Проверьте числовые параметры работы.') from exc

@dataclass(frozen=True)
class WorkPlanParameters:
    title: str
    subject_id: int
    curriculum_subject_id: int
    participant_grade: int
    curriculum_grade: int
    work_type: str
    input_mode: str
    quarter: int | None
    education_track: str | None
    variant_count: int
    language_policy: str

def parse_parameters(values):
    title = str(values.get('title','')).strip()
    if not title or len(title)>255: raise WorkPlanError('Укажите название работы до 255 символов.')
    kind = values.get('work_type')
    if kind not in ('baseline','sor','soch'): raise WorkPlanError('Выберите тип работы.')
    grade = integer(values.get('participant_grade'),1,11)
    curriculum = grade-1 if kind=='baseline' else grade
    if curriculum<1: raise WorkPlanError('Для нулевого контроля нужна программа предыдущего класса. Выберите параллель от 2 класса.')
    subject = integer(values.get('subject_id'),1,2_147_483_647)
    source = integer(values.get('curriculum_subject_id') or subject,1,2_147_483_647) if kind=='baseline' else subject
    quarter = None if kind=='baseline' else integer(values.get('quarter'),1,4)
    track = values.get('education_track') if curriculum in (10,11) else None
    if curriculum in (10,11) and track not in ('general','emn','ogn'): raise WorkPlanError('Выберите направление проверяемой программы.')
    mode = values.get('input_mode')
    if mode not in ('manual','online'): raise WorkPlanError('Выберите бумажное или онлайн-проведение.')
    language = values.get('language_policy')
    if language not in ('auto','ru','kk','both'): raise WorkPlanError('Выберите язык работы.')
    return WorkPlanParameters(title,subject,source,grade,curriculum,kind,mode,quarter,track,
        integer(values.get('variant_count'),2,10),language)

def required_languages(policy):
    if policy not in ('auto','ru','kk','both'): raise WorkPlanError('Выберите язык работы.')
    return ('kk','ru') if policy in ('auto','both') else (policy,)

def participant_language(policy, instruction_language):
    if policy in ('kk','ru'): return policy
    if policy not in ('auto','both'): raise WorkPlanError('Выберите язык работы.')
    return 'ru' if instruction_language=='ru' else 'kk'

def available_quarters(plan):
    return list(range(1,plan.quarter+1)) if plan.quarter is not None else None

def source_quarter_value(plan,value):
    if value in (None,''):return None
    quarter=integer(value,1,4)
    if plan.quarter is not None and quarter>plan.quarter:
        raise WorkPlanError('Нельзя выбирать задания будущих четвертей.')
    return quarter

def item_quarter_allowed(item,plan):
    if plan.quarter is None:return True
    for link in item.objectives:
        objective=getattr(link,'learning_objective',None)
        effective=item.quarter if item.quarter is not None else getattr(objective,'quarter',None)
        if effective is None or not 1<=effective<=plan.quarter:return False
    return bool(item.objectives)

def item_profile(item):
    payload=next(iter(item.payloads.values()))
    grading=payload['grading_settings'];content=payload['content']
    # Compare scoring structure, without comparing translated prose or answers.
    import json
    technical={k:v for k,v in grading.items() if k!='criteria'}
    criteria=tuple(str(c.get('max_score')) for c in grading.get('criteria',[]))
    sizes=tuple((key,len(content[key])) for key in ('parts','statements','items','left','right','options') if isinstance(content.get(key),list))
    if isinstance(content.get('segments'),list):
        sizes+= (('gaps',sum(s.get('type')=='gap' for s in content['segments'])),)
    return (tuple(sorted(g['id'] for g in item.objectives)),item.question_type,
        item.difficulty,Decimal(item.max_score),json.dumps(technical,sort_keys=True),criteria,sizes)

def task_signature(question_type,payloads):
    """Detect duplicate displayed tasks, including mere option/part permutations.

    This is a structural duplicate check, not mathematical equivalence checking.
    """
    import json
    from hashlib import sha256
    payload=payloads.get('kk') or payloads.get('ru')
    def normalized(value,key=''):
        if isinstance(value,dict):
            return {k:normalized(v,k) for k,v in value.items() if k not in ('id','value')}
        if isinstance(value,list):
            result=[normalized(v) for v in value]
            if key in ('options','parts','items','left','right','word_bank'):
                result.sort(key=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True))
            return result
        return value.strip() if isinstance(value,str) else value
    data=dict(question_type=question_type,
        statement=normalized(payload.get('text_segments') or payload.get('text')),
        content=normalized(payload['content']))
    return sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def completeness(plan, items):
    issues=[]
    groups={v:[i for i in items if i.variant_no==v] for v in range(1,plan.variant_count+1)}
    for v,rows in groups.items():
        if not rows: issues.append(('empty',v))
    reference=Counter(item_profile(i) for i in groups[1])
    for v,rows in groups.items():
        if v!=1 and rows and groups[1] and Counter(item_profile(i) for i in rows)!=reference:
            issues.append(('profile',v))
    return issues
