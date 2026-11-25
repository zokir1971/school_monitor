"""Select one side of explicitly catalogued system messages, never arbitrary prose."""
from functools import lru_cache
from pathlib import Path
import json,re,string

@lru_cache(maxsize=1)
def _patterns():
    data=json.loads(Path(__file__).with_suffix('.json').read_text(encoding='utf-8'))
    result=[]
    for source,translations in data.items():
        parts=[];seen=set()
        for literal,field,fmt,conversion in string.Formatter().parse(source):
            parts.append(re.escape(literal))
            if field is not None:
                key='v'+field
                parts.append('(?P='+key+')'if key in seen else '(?P<'+key+'>[\\s\\S]*?)')
                seen.add(key)
        result.append((re.compile(''.join(parts)),translations))
    return tuple(result)


def paired_message(value,language):
    if not isinstance(value,str) or ' / ' not in value:return None
    for regex,translations in _patterns():
        match=regex.fullmatch(value)
        if match:
            return ''.join(literal + (match.group('v'+field) if field is not None else '')
                for literal,field,fmt,conversion in string.Formatter().parse(translations[language]))
    return None
