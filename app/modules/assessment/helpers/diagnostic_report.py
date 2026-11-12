"""Pure report view from frozen presentation, canonical answers and private bindings.
Call only after owner authorization or pupil publication checks.
"""
import copy
from decimal import Decimal
from app.modules.assessment.helpers.question_prose_layout import explanation_blocks as explanation_parts, part_statement_layout, presentation_instruction, EXPLANATION_LAYOUT_VERSION


def expected(spec,item):
    key=item['payload']['answer_key'];path=list(spec['target'])
    if item['question_type']=='formula':
        if spec['kind']=='formula':path=path+['expression'] if path[0]=='parts' else ['expression']
        else:
            path=['variable_meanings' if k=='meanings' else k for k in path]
            if path[0]=='value':path=path[1:]
    elif path[0]=='parts':path[0]='values'
    if path[0]=='pairs' and isinstance(key.get('pairs'),list):
        key={**key,'pairs':{p['left']:p['right'] for p in key['pairs']}}
    if item['question_type']=='short_text':return key.get('accepted_answers',[])
    value=key
    for part in path:
        if not isinstance(value,dict):return []
        value=value.get(part)
    if path[0]=='gaps' and isinstance(value,dict):value=value.get('accepted_answers',[])
    return value if isinstance(value,list) else ([] if value is None else [value])


def display_values(values,control,spec,ru):
    values=values if isinstance(values,list) else ([] if values in (None,'') else [values])
    choices={o['token']:o for o in control.get('choices',[])}
    result=[]
    for value in values:
        if value in ('',None):result.append([dict(type='text',text='—')]);continue
        o=choices.get(str(value))
        if o:
            result.append([dict(type='text',text=o['label']+') '),*o['segments']])
        elif spec['kind']=='boolean':
            v=value is True or value=='true'
            result.append([dict(type='text',text=('Верно' if v else 'Неверно') if ru else ('Дұрыс' if v else 'Бұрыс'))])
        else:result.append([dict(type='latex' if spec['kind']=='formula' else 'text',text=str(value))])
    return result


def build(attempt,answers,ru):
    by_order={a['order_no']:a for a in answers};questions=copy.deepcopy(attempt['presentation'])
    specs=attempt['private_data']['specs'];items=attempt['private_data']['items']
    for index,q in enumerate(questions):
        answer=by_order.get(index+1)
        q.update(answer_id=answer['id'] if answer else None,score=answer['score'] if answer else None,
                 pending=answer is not None and answer['score'] is None,
                 explanation=items[index]['payload'].get('explanation') or '')
        snapshot=(answer or {}).get('diagnostic_snapshot') or {}
        amendment=snapshot.get('explanation_review') or {}
        q['explanation_amended']=bool(snapshot.get('fingerprint') and amendment.get('version')==1 and amendment.get('source_item_fingerprint')==snapshot.get('fingerprint') and isinstance(amendment.get('text'),str))
        if q['explanation_amended']:q['explanation']=amendment['text']
        q['layout_version']=EXPLANATION_LAYOUT_VERSION
        q['score_review_required']=False
        reviewed=amendment.get('reviewed_answers',{}) if q['explanation_amended'] else {}
        if not isinstance(reviewed,dict):reviewed={}
        part_ids={p.get('id') for p in items[index]['payload'].get('content',{}).get('parts',[])}
        q['explanation_blocks']=explanation_parts(q['explanation'],items[index]['payload'],'ru' if ru else 'kk')
        if items[index]['payload'].get('content',{}).get('parts'):
            q['segments']=part_statement_layout(q.get('segments',[]))
            q['instruction']=part_statement_layout([dict(type='text',text=q.get('instruction') or '')])[0]['text']
        q['instruction']=presentation_instruction(q.get('instruction'),q.get('segments',[]))
        multiple=items[index]['question_type']=='multiple_choice' and 'options' in items[index]['payload'].get('content',{})
        q['score_rule']=''
        if multiple and items[index]['payload'].get('grading_settings',{}).get('partial_credit') is False:
            q['score_rule']=('Для полного балла выберите все правильные варианты без лишних. В этой работе за неполный набор начисляется 0 баллов.' if ru else 'Толық балл алу үшін барлық дұрыс нұсқаны артық жауапсыз таңдаңыз. Бұл жұмыста толық емес жауапқа 0 балл қойылады.')
        q['outcome']='pending'  if q['pending'] else ('correct' if q['score']==Decimal(q['max_score']) else 'partial' if q['score'] and q['score']>0 else 'incorrect')
        for block_index,block in enumerate(q['blocks'],1):
            if items[index]['payload'].get('content',{}).get('parts'):block['segments']=part_statement_layout(block.get('segments',[]),block_index)
            controls=[]
            for c in block['controls']:
                spec=specs[c['name']];values=expected(spec,items[index])
                reverse={v:k for k,v in spec['options'].items()}
                correct=[reverse.get(v,v) if isinstance(v,(str,int,float,bool)) else str(v) for v in values]
                actual=attempt['responses'].get(c['name'])
                if multiple and q['outcome']=='incorrect' and isinstance(actual,list) and actual and correct and set(map(str,actual))<set(map(str,correct)):
                    q['outcome']='incomplete' 
                cell=dict(actual=display_values(actual,c,spec,ru),correct=display_values(correct,c,spec,ru))
                path=spec.get('target',[])
                review=reviewed.get(path[1]) if len(path)>1 and path[0]=='parts' and path[1] in part_ids else None
                if isinstance(review,dict):
                    segments=review.get('segments')
                    if isinstance(segments,list) and segments and all(isinstance(s,dict) and s.get('type') in ('text','latex') and isinstance(s.get('text'),str) for s in segments):
                        cell.update(recorded_correct=cell['correct'],correct=[copy.deepcopy(segments)],review_note=str(review.get('note') or ''))
                        q['score_review_required']=True;q['outcome']='needs_review'
                controls.append(cell)
            block['review']=controls;block.pop('controls',None)
    return questions
