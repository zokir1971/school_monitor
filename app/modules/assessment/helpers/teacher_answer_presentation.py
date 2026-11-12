"""Read-only teacher view from the saved question and canonical pupil answer.
No grading, token shuffling, source edits or database access.
"""
from copy import deepcopy
from app.modules.assessment.helpers.question_prose_layout import matching_letter
from app.modules.assessment.helpers.diagnostic_report import display_values


def question_view(row):
    snapshot=getattr(row,'diagnostic_snapshot',None) or {}
    return dict(max_score=getattr(row,'max_score',None),question_type=getattr(row.question_type,'value',row.question_type),text=row.question_text or '',
        text_segments=deepcopy(snapshot.get('text_segments') or [dict(type='text',text=row.question_text or '')]),instruction=getattr(row,'instruction',None) or '',
        content=deepcopy(getattr(row,'content',None) or {}),answer_key=deepcopy(getattr(row,'answer_key',None) or {}),
        grading_settings=deepcopy(getattr(row,'grading_settings',None) or {}),explanation=snapshot.get('explanation') or '')


def response_lines(view,data):
    """Use the same option/LaTeX display as the diagnostic report, without green key styling."""
    content=view['content'];kind=view['question_type'];data=data if isinstance(data,dict) else {};result=[]
    def cell(value,choices=None,style='text',number=None,prefix=None):
        options=[]
        for index,option in enumerate(choices or []):
            segments=option.get('segments') or ([dict(type='image',object_key=option['object_key'],alt=option.get('alt',''))] if option.get('object_key') else [dict(type='text',text=str(option.get('label') or option.get('text') or option.get('value','')))])
            options.append(dict(token=str(option.get('value')),label=matching_letter(index) if kind=='matching' else str(index+1) if kind in ('ordering','fill_gaps') else str(option.get('value','')),segments=segments))
        # display_values expects a scalar or a list of scalars, not mapping keys.
        rendered=display_values(value,dict(choices=options),dict(kind=style),True)
        result.append(dict(number=number,prefix=deepcopy(prefix or []),values=rendered,boolean=style=='boolean',raw=value if style=='boolean' else None))
    def formula(value,part,number=None):
        value=value if isinstance(value,dict) else dict(expression=value)
        cell(value.get('expression',value.get('latex',value.get('value'))),style='formula',number=number)
        meanings=value.get('variable_meanings') or {}
        for symbol in part.get('variables',list(meanings)):
            cell(meanings.get(symbol),part.get('meaning_options'),prefix=[dict(type='latex',text=str(symbol))])
    if not data:return ()
    if kind in ('single_choice','image_choice','number','formula') and content.get('parts'):
        source=data.get('parts' if kind=='formula' else 'values',{})
        source=source if isinstance(source,dict) else {}
        for number,part in enumerate(content['parts'],1):
            raw=source.get(part.get('id'))
            if kind=='formula':formula(raw,part,number)
            else:cell(raw,part.get('options'),number=number)
    elif kind in ('single_choice','multiple_choice','image_choice'):
        cell(data.get('values',[]) if kind=='multiple_choice' else data.get('value'),content.get('options'))
    elif kind=='true_false':
        statements=content.get('statements') or []
        if statements:
            values=data.get('values') or {}
            for number,part in enumerate(statements,1):cell(values.get(part.get('id')),style='boolean',number=number,prefix=part.get('segments'))
        else:cell(data.get('value'),style='boolean')
    elif kind=='matching':
        values=data.get('pairs') or []
        values={r.get('left'):r.get('right') for r in values if isinstance(r,dict)} if isinstance(values,list) else values
        for number,left in enumerate(content.get('left',[]),1):cell(values.get(left.get('value')),content.get('right'),number=number,prefix=left.get('segments'))
    elif kind=='ordering':
        for number,value in enumerate(data.get('order') or [],1):cell(value,content.get('items'),number=number)
    elif kind=='fill_gaps':
        bank=content.get('word_bank') or [];bank=[dict(value=v,segments=[dict(type='text',text=v)]) if isinstance(v,str) else v for v in bank]
        for number,gap in enumerate((s for s in content.get('segments',[]) if s.get('type')=='gap'),1):
            cell((data.get('gaps') or {}).get(gap.get('gap_id')),bank,number=number)
    elif kind=='formula':formula(data,content)
    elif kind in ('short_text','manual_review'):cell(data.get('text',data.get('value')))
    else:cell(data.get('value',data.get('text')))
    return tuple(result)
