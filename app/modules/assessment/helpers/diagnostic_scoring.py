"""Pure token decoding and adapter to existing, versioned grading policies."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from types import SimpleNamespace
from app.modules.assessment.enums import AssessmentQuestionType, AssessmentAnswerStatus
from app.modules.assessment.services.assessment_grading_service import AssessmentGradingService as Grader
from app.modules.assessment.services.assessment_scoring_service import AssessmentScoringService as Totals


def decode(private, responses):
    """Opaque pupil tokens -> existing answer_data contracts. Missing stays missing."""
    result=[{} for _ in private['items']]
    for name,s in private['specs'].items():
        raw=responses.get(name)
        if raw in (None,'',[]):continue
        options=s['options'];kind=s['kind']
        if isinstance(raw,list):value=[options.get(v,'') for v in raw]
        elif kind=='boolean':value=raw=='true'
        else:value=options.get(raw,raw) if not options else options[raw]
        target=list(s['target'])
        question_type=private['items'][s['question']]['question_type']
        if question_type=='formula':
            if kind=='formula':target=target+['expression'] if target[0]=='parts' else ['expression']
            else:
                target=['variable_meanings' if k=='meanings' else k for k in target]
                if target[0]=='value':target=target[1:]
        elif target[0]=='parts':target[0]='values'
        if question_type in ('short_text','manual_review') and target==['value']:target=['text']
        if target[0]=='order':target[0]='order'
        if kind=='number':
            try:
                value=str(Decimal(str(value).replace(',','.').strip()))
                if not Decimal(value).is_finite():value=''
            except InvalidOperation:value=''
        node=result[s['question']]
        for key in target[:-1]:node=node.setdefault(key,{})
        node[target[-1]]=value
    for item,data in zip(private['items'],result):
        if item['question_type']=='matching' and isinstance(data.get('pairs'),dict):
            data['pairs']=[dict(left=k,right=v) for k,v in data['pairs'].items()]
    return result


def grade(item, data):
    p=item['payload'];t=item['question_type'];maximum=Decimal(item['max_score'])
    q=SimpleNamespace(question_type=AssessmentQuestionType(t), content=p['content'],answer_key=p['answer_key'],
                      grading_settings=p.get('grading_settings') or {},max_score=maximum)
    a=SimpleNamespace(answer_data=data,score=None,max_score=maximum,is_correct=None,
                      status=AssessmentAnswerStatus.PENDING_REVIEW,checked_at=None,checked_by_user_id=None)
    invalid_numeric_key=False
    if t=='number' and 'parts' not in q.content and data:
        # Legacy grader accepts numeric Python values; JSON canonical answer stays a string.
        try:
            expected=Decimal(str(q.answer_key['value']).replace(',','.'))
            tolerance=Decimal(str(q.grading_settings.get('tolerance',0)))
            if not expected.is_finite() or not tolerance.is_finite() or tolerance<0:raise ValueError('number_key')
            q.answer_key={**q.answer_key,'value':expected}
            q.grading_settings={**q.grading_settings,'tolerance':tolerance}
        except (InvalidOperation,ValueError,KeyError):invalid_numeric_key=True
        try:
            actual=Decimal(str(data.get('value','')).replace(',','.'))
            a.answer_data={**data,'value':actual if actual.is_finite() else None}
        except InvalidOperation:a.answer_data={**data,'value':None}
    if not data:
        a.score=Decimal(0);a.is_correct=False;a.status=AssessmentAnswerStatus.CHECKED;a.checked_at=datetime.now(timezone.utc)
    elif t not in ('formula','manual_review') and not invalid_numeric_key:
        method=getattr(Grader,'_grade_'+t,None)
        if method:
            try:method(question=q,answer=a,checked_at=datetime.now(timezone.utc))
            except (ValueError,KeyError,TypeError,InvalidOperation,ArithmeticError):
                # Invalid historical keys must never silently give a pupil zero.
                a.score=None;a.is_correct=None;a.status=AssessmentAnswerStatus.PENDING_REVIEW;a.checked_at=None
    if a.score is not None:
        a.score=Decimal(a.score).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        if not a.score.is_finite() or not 0<=a.score<=maximum:raise ValueError('score_range')
    return dict(answer_data=deepcopy(data),score=a.score,max_score=maximum,status=a.status,is_correct=a.is_correct,
                checked_by_user_id=None,checked_at=a.checked_at)


def split_score(value,count):
    """Equal shares in cents, deterministic residual; never duplicate points across goals."""
    if not count:return []
    cents=int((Decimal(value)*100).to_integral_value(rounding=ROUND_HALF_UP));base,rest=divmod(cents,count)
    return [Decimal(base+(i<rest))/100 for i in range(count)]


def final_scores(answers):
    if any(a['score'] is None for a in answers):return None
    return Totals.calculate(score=sum((a['score'] for a in answers),Decimal(0)),
                            max_score=sum((a['max_score'] for a in answers),Decimal(0)))
