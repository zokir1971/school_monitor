"""Language variants preserve the technical contract; only human text is editable."""
from copy import deepcopy
from hashlib import sha256
import json,re

FIELDS=('title','text','text_segments','instruction','content','answer_key','grading_settings','explanation','author_comment')
TEXT_KEYS={'text','label','title','description','prompt','statement','meaning','definition','explanation','caption','alt','hint','label_kz','label_ru'}

def code(value):return str(getattr(value,'value',value))

def source_payload(item):
    return {key:deepcopy(getattr(item,key,None)) for key in FIELDS}

def fingerprint(item):
    data=source_payload(item)
    for name in ['subject_id','grade_level','quarter','question_type','difficulty','max_score','language']:
        value=getattr(item,name,None);data[name]=code(value) if value is not None else None
    data['objectives']=sorted(getattr(o,'learning_objective_id',0) for o in getattr(item,'objectives',[]))
    return sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def target_language(language):
    if code(language) not in ['ru','kk']:raise ValueError('Двуязычная версия доступна для русского и казахского языков.')
    return 'kk' if code(language)=='ru' else 'ru'

def statement_slots(payload):
    """Virtual boundary text slots; source storage and fingerprint stay unchanged."""
    result = deepcopy(payload)
    segments = result.get('text_segments')
    if not segments or not all(isinstance(s,dict) and s.get('type') in {'text','latex','image'} for s in segments):
        return result
    segments = list(segments)
    if segments[0]['type'] != 'text':segments.insert(0,dict(type='text',text=''))
    if segments[-1]['type'] != 'text':segments.append(dict(type='text',text=''))
    result['text_segments'] = segments
    return result

def _all_translation_fields(payload,question_type):
    payload=statement_slots(payload)
    result=[]
    def walk(value,path):
        if isinstance(value,dict):
            # Formula and image storage values are shared, never translated.
            for key,child in value.items():
                if value.get('type')=='latex' or key in {'latex','url','object_key','image_url','value','key','id','code'}:continue
                if isinstance(child,str) and (key in TEXT_KEYS or (code(question_type)=='true_false' and path==('content','labels') and key in {'true','false'})) and (child.strip() or (path and path[0]=='text_segments' and value.get('type')=='text')):result.append((path+(key,),child))
                elif isinstance(child,(dict,list)):walk(child,path+(key,))
        elif isinstance(value,list):
            for index,child in enumerate(value):
                if isinstance(child,str):
                    # Only textual accepted answers and word-bank strings are language data.
                    if path and path[-1] in {'accepted_answers','word_bank','labels'} and code(question_type) in {'short_text','fill_gaps','true_false'}:
                        if child.strip() and not any(c in child for c in '\\=∪∩{}^0123456789'):result.append((path+(index,),child))
                else:walk(child,path+(index,))
    for key in FIELDS:
        value=payload.get(key)
        if isinstance(value,str) and value.strip():result.append(((key,),value))
        elif isinstance(value,(dict,list)):walk(value,(key,))
    return result

def _translation_group(path,text):
    if path[0] in {'text','text_segments'}:return ('statement',text) if text.strip() else ('slot',path)
    if 'accepted_answers' in path or 'word_bank' in path:return ('accepted',text)
    return ('field',path)


def translation_fields(payload,question_type):
    # Reuse the statement projection and textual answer-bank entries. Other
    # fields retain context: the same word can have different meanings.
    unique={}
    for path,text in _all_translation_fields(payload,question_type):unique.setdefault(_translation_group(path,text),(path,text))
    return list(unique.values())

def get_value(payload,path):
    if path and path[0]=='text_segments':payload=statement_slots(payload)
    for key in path:payload=payload[key]
    return payload

def make_variant(source,question_type,values):
    source=statement_slots(source)
    fields=translation_fields(source,question_type);expected={f'f{i}' for i in range(len(fields))}
    if set(values)!=expected:raise ValueError('Состав полей перевода изменился. Обновите страницу.')
    payload=deepcopy(source)
    projected_statement = None
    segments = source.get('text_segments')
    if segments and all(isinstance(s,dict) and s.get('type') in {'text','latex','image'} for s in segments):
        translations = {_translation_group(path, original): values[f'f{i}']
                        for i,(path,original) in enumerate(fields)}
        projected_statement = ''.join(
            translations.get(_translation_group(('text_segments',index,'text'),segment.get('text','')),segment.get('text',''))
            if segment['type']=='text' else '[Сурет]' if segment['type']=='image' else segment.get('text','')
            for index,segment in enumerate(segments)).strip()
    for i,(path,original) in enumerate(fields):
        value=values[f'f{i}']
        optional_text = path[0]=='text_segments' and path[-1]=='text'
        if not isinstance(value,str) or (not value.strip() and not optional_text):raise ValueError('Заполните все поля перевода.')
        if len(value)>max(20000,len(original)*5):raise ValueError('Перевод превышает допустимый размер.')
        numeric=lambda text:sorted(token.replace(',','.') for token in re.findall(r"[−-]?\d+(?:[.,]\d+)?",text.replace('−','-')))
        latex=lambda text:re.findall(r'\$[^$]+\$|\\\([^)]*\\\)',text)
        # The editor projects protected rich tokens into plain text without
        # LaTeX delimiters. Validate those tokens in their segments, not twice
        # through a differently formatted plain-text fallback.
        is_projection = path == ('text',) and projected_statement is not None and value.strip() == projected_statement
        if not is_projection and (numeric(value)!=numeric(original) or latex(value)!=latex(original)):
            raise ValueError('Перевод должен сохранять числа и формулы исходного задания. Поле: ' + '.'.join(map(str,path)))

        for linked_path,linked_text in _all_translation_fields(source,question_type):
            if _translation_group(linked_path,linked_text)!=_translation_group(path,original):continue
            node=payload
            for key in linked_path[:-1]:node=node[key]
            # Spaces next to math segments join words and formulas. They are
            # meaningful presentation data, not a technical contract change.
            segment_text = linked_path[-1] == 'text' and (
                linked_path[0] == 'text_segments' or 'segments' in linked_path)
            node[linked_path[-1]] = value if segment_text else value.strip()
    return payload

def assert_variant_contract(source,target,question_type):
    source=statement_slots(source);target=statement_slots(target)
    fields=translation_fields(source,question_type)
    values={f'f{i}':get_value(target,path) for i,(path,_) in enumerate(fields)}
    rebuilt = make_variant(source,question_type,values)
    if rebuilt != target:
        path = first_contract_difference(rebuilt, target)
        raise ValueError('Перевод изменяет структуру, формулы или правильные ответы задания. Поле: ' + path)


def first_contract_difference(left, right, path='$'):
    """Technical JSON path only: never expose source text, solutions or API data."""
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            key = sorted(set(left) ^ set(right), key=str)[0]
            return path + '.' + str(key)
        for key in left:
            if left[key] != right[key]:
                return first_contract_difference(left[key], right[key], path + '.' + str(key))
    elif isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        if len(left) != len(right):
            return path + '.length'
        for index, (a, b) in enumerate(zip(left, right)):
            if a != b:
                return first_contract_difference(a, b, path + '[' + str(index) + ']')
    return path
