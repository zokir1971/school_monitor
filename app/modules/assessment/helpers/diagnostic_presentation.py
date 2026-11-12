"""Explicit public allowlist; private answer bindings never enter the pupil HTML."""
import copy
import re
import secrets
from collections import Counter

TYPES = {'single_choice','multiple_choice','image_choice','true_false','number','short_text','formula','manual_review','matching','ordering','fill_gaps'}
# Relative labels become invalid after shuffling. Require editorial correction first.
ALPHABET = 'АБВГДЕЖЗИКЛМНОПРСТУФХЦЧШЩЭЮЯ'
RELATIVE = re.compile(r'(?i)(все\s+(?:выше|перечислен|ответ)|ни\s+один\s+из|оба\s+ответ|all\s+(?:of\s+the\s+)?above|none\s+of|жоғарыдағ|барлық\s+(?:жауап|нұсқа)|(?:вариант|ответ|нұсқа|жауап)[\s:]+[A-DА-Г](?:\s*(?:и|или|және|немесе|,|/)\s*[A-DА-Г])+)')


def segments(raw):
    result = []
    for s in raw or []:
        if s.get('type') in ('text','latex'):
            result.append({'type':s['type'], 'text':str(s.get('text',''))})
        elif s.get('type') == 'image':
            from app.modules.assessment.services.question_bank_media_service import MEDIA_KEY_PATTERN
            key = s.get('object_key','')
            if not MEDIA_KEY_PATTERN.fullmatch(key):
                raise ValueError('image')
            result.append({'type':'image','object_key':key,'alt':str(s.get('alt',''))})
    return result


def compile_presentation(rows, language):
    """Public controls use random tokens, never answer letters or bank identifiers."""
    public, specs, private = [], {}, []
    rng = secrets.SystemRandom()
    positions = Counter()
    for row in rows:
        t = row['question_type']
        if t not in TYPES:
            raise ValueError('type')
        p = copy.deepcopy(row['payloads'][language])
        content, key = p['content'], p['answer_key']
        qi = len(public)
        q = dict(number=qi+1, question_type=t, max_score=str(row['max_score']),
                 segments=segments(p.get('text_segments')) or [{'type':'text','text':p.get('text','')}],
                 instruction=p.get('instruction') or '', blocks=[], bank=[])
        private.append(dict(question_type=t, max_score=str(row['max_score']), payload=p, objectives=copy.deepcopy(row.get('objectives',[]))))

        def control(kind, target, choices=None, correct=None, multi=False):
            name = f'f{len(specs)}'
            mapping, offered = {}, []
            options = copy.deepcopy(choices or [])
            if kind in ('choice','multi','bank','meaning'):
                for o in options:
                    prose=' '.join(s.get('text','') for s in o.get('segments',[]) if s.get('type')=='text')+' '+o.get('label','')
                    if RELATIVE.search(prose):
                        raise ValueError('relative_labels')
                rng.shuffle(options)
                if kind == 'choice' and correct is not None:
                    matches=[o for o in options if o.get('value')==correct]
                    if len(matches)!=1:raise ValueError('answer')
                    good=matches[0];options.remove(good)
                    lowest=min(positions[(len(options)+1,j)] for j in range(len(options)+1))
                    index=rng.choice([j for j in range(len(options)+1) if positions[(len(options)+1,j)]==lowest])
                    positions[(len(options)+1,index)]+=1;options.insert(index,good)
                for index, o in enumerate(options):
                    token=secrets.token_urlsafe(12);mapping[token]=o['value']
                    ss=segments(o.get('segments'))
                    if o.get('object_key'):ss=segments([dict(type='image',object_key=o['object_key'],alt=o.get('alt',''))])
                    if not ss:ss=[{'type':'text','text':o.get('label',o.get('text',''))}]
                    offered.append(dict(token=token,label=(ALPHABET[index] if index<len(ALPHABET) else str(index+1)) if kind=='bank' else (chr(65+index) if index<26 else str(index+1)),segments=ss))
            elif kind in ('matching','ordering'):
                # ordering: tokens identify items; displayed numbers are fresh positions.
                rng.shuffle(options)
                for index,o in enumerate(options):
                    token=secrets.token_urlsafe(12);mapping[token]=o['value']
                    offered.append(dict(token=token,label=str(index+1) if kind=='ordering' else (ALPHABET[index] if index<len(ALPHABET) else str(index+1)),segments=segments(o.get('segments'))))
            specs[name]=dict(question=qi,kind=kind,target=target,options=mapping,multi=multi)
            return dict(name=name,kind=kind,choices=offered,multi=multi)

        def block(ss=None, c=None, number=None):
            b=dict(segments=segments(ss),controls=c or [],number=number);q['blocks'].append(b);return b

        if t in ('single_choice','image_choice'):
            if 'parts' in content:
                for n,part in enumerate(content['parts'],1):
                    block(part.get('segments'),[control('choice',['parts',part['id']],part['options'],key['values'][part['id']])],n)
            else:block(c=[control('choice',['value'],content['options'],key['value'])])
        elif t=='multiple_choice':block(c=[control('multi',['values'],content['options'],multi=True)])
        elif t=='true_false':
            for n,part in enumerate(content.get('statements',[{}]),1):
                c=control('boolean',['values',part['id']] if 'id' in part else ['value'])
                c['choices']=[dict(token='true',label='Верно' if language=='ru' else 'Дұрыс',segments=[]),dict(token='false',label='Неверно' if language=='ru' else 'Бұрыс',segments=[])]
                block(part.get('segments'),[c],n if 'id' in part else None)
        elif t in ('number','formula'):
            for n,part in enumerate(content.get('parts',[content]),1):
                target=['parts',part['id']] if 'id' in part else ['value']
                b=block(part.get('segments'),[control(t,target)],n if 'id' in part else None)
                b['unit']=part.get('unit','')
                if t=='formula':
                    for variable in part.get('variables',[]):
                        c=control('meaning',target+['meanings',variable],part.get('meaning_options',[]));c['variable']=variable;b['controls'].append(c)
        elif t in ('short_text','manual_review'):block(c=[control('long' if t=='manual_review' else 'text',['value'])])
        elif t=='matching':
            shared=control('matching',['pairs'],content['right'])
            mapping=specs.pop(shared['name'])['options']
            q['bank']=shared['choices']
            for n,left in enumerate(content['left'],1):
                name=f'f{len(specs)}'
                specs[name]=dict(question=qi,kind='matching',target=['pairs',left['value']],options=mapping,multi=False)
                block(left.get('segments'),[dict(name=name,kind='matching',choices=q['bank'],multi=False)],n)
        elif t=='ordering':
            c=control('ordering',['order'],content['items']);q['bank']=c['choices'];block(c=[c])
        elif t=='fill_gaps':
            rich=content.get('input_mode')=='word_bank'
            bank=content.get('word_bank',[])
            if rich and bank and isinstance(bank[0],str):bank=[dict(value=v,segments=[dict(type='text',text=v)]) for v in bank]
            shared=control('bank',['bank'],bank) if rich else None
            mapping=specs.pop(shared['name'])['options'] if shared else {}
            if shared:q['bank']=shared['choices']
            for s in content.get('segments',[]):
                if s.get('type')!='gap':block([s]);continue
                if rich:
                    name=f'f{len(specs)}';specs[name]=dict(question=qi,kind='bank',target=['gaps',s['gap_id']],options=mapping,multi=False)
                    c=dict(name=name,kind='bank',choices=q['bank'],multi=False)
                else:c=control('text',['gaps',s['gap_id']])
                block(c=[c])
        public.append(q)
    return public, dict(items=private,specs=specs)


def validate_responses(raw, specs):
    if not isinstance(raw,dict) or set(raw)-set(specs):raise ValueError('fields')
    result={}
    for name,value in raw.items():
        s=specs[name];kind=s['kind']
        if kind=='ordering':
            if not isinstance(value,list) or len(value)!=len(s['options']) or any(not isinstance(v,str) or (v and v not in s['options']) for v in value) or len([v for v in value if v])!=len({v for v in value if v}):raise ValueError('order')
        elif s['multi']:
            if not isinstance(value,list) or len(value)>len(s['options']) or any(not isinstance(v,str) or v not in s['options'] for v in value) or len(set(value))!=len(value):raise ValueError('options')
        else:
            if not isinstance(value,str) or len(value)>(20000 if kind=='long' else 10000):raise ValueError('text')
            if value and kind in ('choice','matching','bank','meaning') and value not in s['options']:raise ValueError('option')
            if value and kind=='boolean' and value not in ('true','false'):raise ValueError('boolean')
        result[name]=value
    return result


def image_keys(presentation):
    found=set()
    def walk(node):
        if isinstance(node,dict):
            if node.get('type')=='image':found.add(node['object_key'])
            for v in node.values():walk(v)
        elif isinstance(node,list):
            for v in node:walk(v)
    walk(presentation);return found
