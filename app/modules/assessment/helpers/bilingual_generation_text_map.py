"""Build target language from one protected source and editable text only.

Pointers address physical source JSON paths. No API/SQL or technical repair.
"""
import re
from app.modules.assessment.helpers.bilingual_question_contract import (
    _all_translation_fields, _translation_group, translation_fields,
    statement_slots, make_variant, assert_variant_contract)


def pointer(path):
    return '/' + '/'.join(str(key).replace('~', '~0').replace('/', '~1') for key in path)


def text_map_fields(source, question_type):
    """Return pointer -> (group, source text), without redundant plain statement."""
    segments = source.get('text_segments') or []
    prefix = bool(segments and segments[0].get('type') != 'text')
    suffix = bool(segments and segments[-1].get('type') != 'text')
    virtual = statement_slots(source)
    allowed = {}
    for path, text in _all_translation_fields(source, question_type):
        if path == ('text',) and segments:
            continue
        address = path
        if path[0] == 'text_segments' and len(path) >= 3:
            index = path[1]
            if prefix and index == 0:
                key = '$prefix'
            elif suffix and index == len(virtual['text_segments'])-1:
                key = '$suffix'
            else:
                address = (path[0], index-int(prefix), *path[2:])
                key = pointer(address)
        else:
            key = pointer(address)
        allowed[key] = (_translation_group(path,text),text)
    return allowed


def normalize_pointer(key):
    """Accept JSON Pointer or a simple JSONPath spelling; never evaluate paths."""
    if not isinstance(key,str) or len(key)>300:
        raise ValueError('Invalid translation field address.')
    if key in {'$prefix','$suffix'} or key.startswith('/'):
        return key
    candidate = key[2:] if key.startswith('$.') else key
    if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*(?:(?:\.[A-Za-z_][A-Za-z_0-9]*)|(?:\[[0-9]+\]))*',candidate):
        raise ValueError('Invalid translation field address.')
    parts = re.findall(r'[A-Za-z_][A-Za-z_0-9]*|[0-9]+',candidate)
    return pointer(parts)


def safe_field_label(key):
    if isinstance(key,str) and len(key)<=160 and re.fullmatch(r'(?:/[A-Za-z_0-9~.-]+)+|\$(?:prefix|suffix)',key):
        return key
    return '<invalid-field-address>'


def source_value(source, key):
    node = source
    try:
        for part in key[1:].split('/'):
            part=part.replace('~1','/').replace('~0','~')
            if isinstance(node,list):
                if not re.fullmatch(r'0|[1-9][0-9]*',part):return False,None
                node=node[int(part)]
            elif isinstance(node,dict):node=node[part]
            else:return False,None
        return True,node
    except (KeyError,IndexError,TypeError,ValueError):
        return False,None


def identical_scalar(original, copied):
    if type(original) is str:
        return type(copied) is str and original==copied
    if original is None:
        return copied is None
    # Numeric or boolean protected values are not translation strings.
    # Exact typed copies can be safely discarded; converted values cannot.
    return type(original) is type(copied) and isinstance(original,(int,float,bool)) and original==copied


def variant_from_text_map(source, question_type, text_map):
    if not isinstance(text_map, dict) or len(text_map) > 5000:
        raise ValueError('Translation text map must be an object.')
    normalized = {}
    for key,value in text_map.items():
        address = normalize_pointer(key)
        if address in normalized and normalized[address] != value:
            raise ValueError('Conflicting translation field aliases: '+safe_field_label(address))
        normalized[address] = value
    text_map = normalized
    allowed = text_map_fields(source, question_type)
    # Plain statement is redundant when rich segments exist. For a sole text
    # segment it is also a valid alias; otherwise the segment projection wins.
    if source.get('text_segments') and '/text' in text_map:
        plain = text_map.pop('/text')
        if not isinstance(plain,str):
            raise ValueError('Translation /text must be a string.')
        segments = source['text_segments']
        if len(segments)==1 and segments[0].get('type')=='text':
            address='/text_segments/0/text'
            if address in text_map and text_map[address] != plain:
                raise ValueError('Conflicting plain and segmented statement translations.')
            text_map[address]=plain
    for address in set(text_map)-set(allowed):
        found,original = source_value(source,address)
        if found and identical_scalar(original,text_map[address]):
            # Ignore ONLY an identical copy; never apply a technical mutation.
            del text_map[address]
        else:
            reason = 'Protected field changed' if found else 'Unknown translation field'
            raise ValueError(reason+': '+safe_field_label(address))
    groups = {}
    for key,value in text_map.items():
        if not isinstance(value,str):
            raise ValueError('Translation values must be strings.')
        group,_ = allowed[key]
        if group in groups and groups[group] != value:
            raise ValueError('Repeated statement/answer text must be translated consistently.')
        groups[group] = value
    fields = translation_fields(source,question_type)
    segments = statement_slots(source).get('text_segments') or []
    values = {}
    for index,(path,original) in enumerate(fields):
        group = _translation_group(path,original)
        if path == ('text',) and segments:
            continue  # Derived after translating physical text segments.
        if group in groups:
            value = groups[group]
        elif not original.strip() or not re.search(r'[^\W\d_]',original, re.UNICODE):
            value = original  # Empty slots and language-free numeric/punctuation text.
        else:
            raise ValueError('Missing translated text field: '+pointer(path))
        values[f'f{index}'] = value
    if segments:
        by_group = dict(groups)
        by_group.update({_translation_group(path,original):values[f'f{i}']
                    for i,(path,original) in enumerate(fields) if f'f{i}' in values})
        projected = ''.join(
            by_group.get(_translation_group(('text_segments',i,'text'),seg.get('text','')),seg.get('text',''))
            if seg['type']=='text' else '[Сурет]' if seg['type']=='image' else seg.get('text','')
            for i,seg in enumerate(segments)).strip()
        for i,(path,original) in enumerate(fields):
            if path == ('text',):
                # If plain text and a sole text segment share a group, its
                # translation is already supplied by the physical segment.
                group = _translation_group(path,original)
                if group in groups:
                    projected = groups[group].strip() if len(segments)==1 else projected
                values[f'f{i}'] = projected
    target = make_variant(source,question_type,values)
    assert_variant_contract(source,target,question_type)
    return target
