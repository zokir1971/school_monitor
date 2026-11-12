"""One explanation layout for every question type; no SQL or grading changes."""
import re

EXPLANATION_LAYOUT_VERSION = 144

EXPLANATION_AUTHORING_RULES = r'''
EXPLANATION STANDARD (all eleven question types, both kk and ru):
Use meaningful task headings "Есеп 1." / "Задача 1." for independent tasks.
Never expose P1/P2/L1/R3 in explanatory prose; keep technical IDs unchanged in JSON.
Explain the rule/formula, show the necessary steps and give a concrete answer.
Use a separate paragraph per task or step. Encode a newline as \n in JSON.
Kazakh step headings: "1-қадам."; Russian: "Шаг 1.".
Wrap EACH mathematical expression in explicit \\( ... \\) or \\[ ... \\] delimiters
inside explanation strings, escaped correctly for JSON. Do not put prose inside math.
For equations include all solutions on the EXACT specified interval and its endpoints.
Use = for exact equality, approximately-equal for approximations; preserve precision.
Do not refer to fixed option letters or array positions: options can be shuffled.
Describe the answer by its value/formula/content. A/B event names in probability are valid.
Explain every independently answered part/pair, not only the first one.
Keep the same mathematics, numeric/formula tokens and reasoning in RU and KK.
For conceptual questions explain the reason briefly; do not invent calculations.
For manual_review explain the expected reasoning/criteria without inventing a unique answer.
Never silently change answer keys, scores, intervals or conditions to fit an explanation.
This explanation standard replaces any earlier instruction requiring plain Unicode-only math
or P/L/R/option-letter references in explanations. It does not alter any JSON answer contract.
'''

def _field(item,name,default=None):
    if isinstance(item,dict):return item.get(name,default)
    return getattr(item,name,default)


def _language(item,language=None,text=''):
    language=language or _field(item,'language')
    language=str(getattr(language,'value',language) or '')
    if language in ('kk','ru'):return language
    return 'kk' if re.search('[әғқңөұүһіӘҒҚҢӨҰҮҺІ]',text) else 'ru'


def _segment_text(segments):
    values=[]
    for segment in segments or []:
        if segment.get('type')=='image':return None
        value=segment.get('text','')
        values.append('\\('+value+'\\)' if segment.get('type')=='latex' else value)
    return ''.join(values).strip()


_MATH = re.compile(r'[A-Za-z0-9_\\{}()\[\].,;:+\-−–=*/^<>≤≥≠≈∈∉∩∪·×πθλ∞√²³⁴⁵⁶⁷⁸⁹αβγδΔΣσΩωĀ̄| \t]+')
_PROTECTED = re.compile(r'\\\(.*?\\\)|\\\[.*?\\\]',re.DOTALL)


def _latex(value):
    # Lexical notation only: never solve, simplify or change parentheses/endpoints.
    value=value.replace('−','-').replace('×',r'\times ').replace('·',r'\cdot ')
    for symbol,command in {'π':r'\pi ','θ':r'\theta ','λ':r'\lambda ','∞':r'\infty ','≤':r'\le ','≥':r'\ge ','≠':r'\ne ','≈':r'\approx ','∈':r'\in ','∉':r'\notin ','∩':r'\cap ','∪':r'\cup '}.items():value=value.replace(symbol,command)
    for number,symbol in enumerate('⁰¹²³⁴⁵⁶⁷⁸⁹'):value=value.replace(symbol,'^{'+str(number)+'}')
    value=re.sub(r'√(\d+|[A-Za-z])',lambda m:r'\sqrt{'+m.group(1)+'}',value)
    value=re.sub(r'(?<![\\A-Za-z])(sin|cos|tan|cot|ln|log)(?=[\s(0-9A-Za-z^])',lambda m:'\\'+m.group(1)+' ',value)
    return value.strip()


def _legacy_math(text):
    def replace(match):
        original=match.group();value=original.strip(' \t.,;:')
        if not value:return original
        if not (re.search(r'[=≈≤≥∈∉πθ√²³∞∩∪]|\\[A-Za-z]+',value) or re.search(r'\d\s*[/+*−-]\s*\d',value)):return original
        # An ordinary Latin phrase containing spaces is not a formula.
        words=re.findall(r'(?<!\\)\b[A-Za-z]{3,}\b',value)
        if any(w.lower() not in {'sin','cos','tan','cot','log','sqrt','frac','left','right','infty','theta','lambda','cdot','times','approx','mathrm','pi','in','notin','cap','cup','le','ge','ne','text','bar','lim'} for w in words):return original
        left=len(original)-len(original.lstrip(' \t.,;:'));right=len(original.rstrip(' \t.,;:'))
        heading=re.match(r'^\d+\.\s+',value);prefix=heading.group() if heading else ''
        if heading:value=value[heading.end():]
        return original[:left]+prefix+'\\('+_latex(value)+'\\)'+original[right:]
    return _MATH.sub(replace,text)


def math_layout(text):
    """Keep explicit math byte-for-byte; only legacy plain spans need detection."""
    parts=[];offset=0
    for match in _PROTECTED.finditer(text):
        parts.extend((_legacy_math(text[offset:match.start()]),match.group()));offset=match.end()
    parts.append(_legacy_math(text[offset:]));return ''.join(parts)


def _task_words(text):
    for source,target in {
        'Әрбір бөліктегі':'Әр есептегі','Әрбір бөлікте':'Әр есепте',
        'әрбір бөліктегі':'әр есептегі','әрбір бөлікте':'әр есепте',
        'Әр бөліктегі':'Әр есептегі','Әр бөлікте':'Әр есепте',
        'Әрбір тармақта':'Әр есепте','әрбір тармақта':'әр есепте',
        'В каждой части':'В каждой задаче','в каждой части':'в каждой задаче',
        'В каждом пункте':'В каждой задаче','в каждом пункте':'в каждой задаче',
    }.items():text=re.sub(r'\s+'.join(map(re.escape,source.split())),lambda match:target,text)
    return text


def explanation_layout(value,item=None,language=None):
    text=str(value or '').replace('\r\n','\n').replace('\r','\n')
    protected={};token_prefix='⟦EXPLICIT_MATH_'
    while token_prefix in text:token_prefix+='X'
    def protect(match):
        token=token_prefix+str(len(protected))+'⟧';protected[token]=match.group();return token
    text=_PROTECTED.sub(protect,text)
    lang=_language(item,language,text);task='Есеп' if lang=='kk' else 'Задача'
    content=_field(item,'content',{}) or {};parts=content.get('parts',[])
    multi=bool(parts or content.get('left'))
    marker=r'(?:[PL]\d+\s*[:.]|P\d+\s+үшін|P\d+[-‐‑‒–—−](?:де|да|те|та)|(?:Часть|Пункт|Задание|Задача|Тапсырма|Есеп)\s+\d+\s*[.:]|\d+[-‐‑‒–—−](?:бөлік|тармақ|тапсырма)\s*[.:])'
    text=re.sub(r'[^\S\n]+(?='+marker+r')','\n\n',text,flags=re.I)
    text=re.sub(r'(?m)^\s*(?:Часть|Пункт|Задание|Задача|Тапсырма|Есеп)\s+(\d+)\s*[.:]\s*',lambda m:task+' '+m.group(1)+'. ',text)
    text=re.sub(r'(?m)^\s*(\d+)\s*[-‐‑‒–—−]\s*(?:бөлік|тармақ|тапсырма)\s*[.:]\s*',lambda m:task+' '+m.group(1)+'. ',text)
    for index,part in enumerate(parts,1):
        key=re.escape(str(part.get('id','')))
        if key:text=re.sub(rf'(?m)^\s*(?:(?:Для|В)\s+)?{key}(?:\s+үшін|[-‐‑‒–—−](?:де|да|те|та))?\b\s*[:.]?\s*',task+' '+str(index)+'. ',text)
    labels={}
    for side in ('left','right'):
        for index,option in enumerate(content.get(side,[]),1):
            identifier=str(option.get('value',''))
            if side=='left':
                text=re.sub(r'(?m)^\s*'+re.escape(identifier)+r'\s*[:.]\s*',task+' '+str(index)+'. ',text)
            else:
                meaning=_segment_text(option.get('segments'))
                if identifier and meaning:labels[identifier]=meaning
    if labels:text=re.sub(r'\bR\d+\b',lambda m:labels.get(m.group(),m.group()),text)
    if multi:text=re.sub(r'(?m)^\s*(\d+)[).]\s+',lambda m:task+' '+m.group(1)+'. ',text)
    # Derive source option descriptions, never assume pupil-visible shuffled labels.
    def descriptions(group):
        return {str(option.get('value','')):value for option in group.get('options',[]) if (value:=_segment_text(option.get('segments')))}
    def references(prose,options):
        prose=re.sub(r'(?i)((?:правильный\s+ответ|дұрыс\s+жауап)\s*[—:\-]?\s*)([A-D])\b',lambda m:m.group(1)+options.get(m.group(2),m.group(2)),prose)
        prose=re.sub(r'(?i)\b([A-D])\s+(и|және)\s+([A-D])\s+(правильные|дұрыс)\b',lambda m:options.get(m.group(1),m.group(1))+' '+m.group(2)+' '+options.get(m.group(3),m.group(3))+' '+m.group(4),prose)
        prose=re.sub(r'(?i)\b(Ответ|Вариант)\s+([A-D])\b',lambda m:m.group(1)+' «'+options.get(m.group(2),m.group(2))+'»',prose)
        prose=re.sub(r'\b([A-D])\s+(жауабы|жауабындағы)\b',lambda m:'«'+options.get(m.group(1),m.group(1))+'» '+m.group(2),prose)
        return prose
    if parts:
        headings=list(re.finditer(r'(?m)^(?:Есеп|Задача)\s+(\d+)\.',text))
        output=[];offset=0
        for index,heading in enumerate(headings):
            output.append(text[offset:heading.start()]);end=headings[index+1].start() if index+1<len(headings) else len(text)
            number=int(heading.group(1));block=text[heading.start():end]
            output.append(references(block,descriptions(parts[number-1])) if 1<=number<=len(parts) else block);offset=end
        output.append(text[offset:]);text=''.join(output)
    else:text=references(text,descriptions(dict(options=content.get('options',[]))))
    text=re.sub(r'(?m)^\s*(\d+)\)\s*',lambda m:(task+' '+m.group(1)+'. ' if multi else (m.group(1)+'-қадам. ' if lang=='kk' else 'Шаг '+m.group(1)+'. ')),text)
    if multi:text=re.sub(r'(?m)^\s*(\d+)\.\s+',lambda m:task+' '+m.group(1)+'. ',text)
    text=re.sub(r'\n(?=(?:Есеп|Задача|Шаг)\s+\d+\.|\d+-қадам\.)','\n\n',text)
    text=re.sub(r'\n{3,}','\n\n',text).strip()
    result=math_layout(text)
    for token,original in protected.items():result=result.replace(token,original)
    return result


def explanation_blocks(value,item=None,language=None):
    result=[]
    for paragraph in re.split(r'\n\s*\n',explanation_layout(value,item,language)):
        if not paragraph:continue
        segments=[];offset=0
        for match in re.finditer(r'\\\((.*?)\\\)|\\\[(.*?)\\\]',paragraph,re.DOTALL):
            if match.start()>offset:segments.append(dict(type='text',text=paragraph[offset:match.start()]))
            segments.append(dict(type='latex',text=match.group(1) if match.group(1) is not None else match.group(2)));offset=match.end()
        if offset<len(paragraph):segments.append(dict(type='text',text=paragraph[offset:]))
        result.append(segments)
    return result

def presentation_instruction(instruction,common_segments):
    """Hide only an exactly known generic instruction already ending the stem."""
    instruction=_task_words(str(instruction or ''))
    def canonical(value):return re.sub(r'\s+',' ',value).strip(' .!\t\r\n').casefold()
    common=canonical(' '.join(s.get('text','') for s in common_segments or [] if s.get('type')=='text'))
    choices={
        'бір дұрыс жауапты таңдаңыз':['бір дұрыс жауапты таңдаңыз','әр есепте бір дұрыс жауапты таңдаңыз','әрбір есепте бір дұрыс жауапты таңдаңыз'],
        'выберите один правильный ответ':['выберите один правильный ответ','в каждой задаче выберите один правильный ответ','выберите один правильный ответ в каждой задаче'],
        'барлық дұрыс жауаптарды таңдаңыз':['барлық дұрыс жауаптарды таңдаңыз'],
        'выберите все правильные ответы':['выберите все правильные ответы'],
    }
    for action,forms in choices.items():
        if canonical(instruction) in forms and common.endswith(action):return ''
    return instruction


def part_statement_layout(segments, index=None, common_segments=None):
    result = [dict(segment) for segment in (segments or [])]
    for segment in result:
        if segment.get('type')=='text':segment['text']=_task_words(segment.get('text',''))
    if common_segments is not None and len(result)==1 and result[0].get('type')=='text':
        result[0]['text']=presentation_instruction(result[0]['text'],common_segments)
    if index is not None and result and result[0].get('type') == 'text':
        # Remove only the matching leading heading; render supplies it once.
        number = re.escape(str(index))
        prefix = rf'^\s*(?:(?:Часть|Пункт|Задание|Задача|Тапсырма|Есеп)\s+{number}|[PР]{number}|{number}\s*[-‐‑‒–—−]\s*(?:бөлік|тармақ|тапсырма))\s*[.:]\s*'
        for _ in range(3):
            value=result[0].get('text','');clean=re.sub(prefix,'',value,count=1,flags=re.IGNORECASE)
            result[0]['text']=clean
            if clean==value:break
    return result


MATCHING_ALPHABET = 'АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЭЮЯ'


def matching_letter(index):
    number = int(index) + 1
    result = ''
    while number > 0:
        number, digit = divmod(number - 1, len(MATCHING_ALPHABET))
        result = MATCHING_ALPHABET[digit] + result
    return result


def matching_label(value, options, side='left'):
    for index, option in enumerate(options or []):
        if option.get('value') == value:
            return str(index + 1) if side == 'left' else matching_letter(index)
    return '—'
