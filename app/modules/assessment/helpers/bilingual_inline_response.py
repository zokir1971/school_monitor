"""Inline bilingual prose; mathematical and structural fields remain shared.

This is a wire adapter, not a contract relaxation. Existing text-map validation
still decides which fields may be translated and checks numbers and formulas.
"""
from copy import deepcopy


def expand_inline_response(raw):
    if not isinstance(raw, dict):
        raise ValueError('AI response must be an object.')
    translation = raw.get('translation')
    if not isinstance(translation, dict) or translation.get('mode') != 'inline_v1':
        return raw
    if set(translation) != {'language', 'mode'}:
        raise ValueError('Inline translation contains unexpected fields.')
    questions = raw.get('questions')
    if not isinstance(questions, list) or not 1 <= len(questions) <= 10:
        raise ValueError('Inline response requires from 1 to 10 questions.')
    maps = []

    def visit(node, path, translations, depth=0):
        if depth > 30:
            raise ValueError('AI response is nested too deeply.')
        if isinstance(node, dict):
            if set(node) == {'source', 'translation'}:
                if not all(isinstance(v, str) for v in node.values()):
                    raise ValueError('Bilingual prose must contain two strings.')
                address = '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in path)
                translations[address] = node['translation']
                return node['source']
            return {key: visit(value, (*path, key), translations, depth+1) for key, value in node.items()}
        if isinstance(node, list):
            return [visit(value, (*path, index), translations, depth+1) for index, value in enumerate(node)]
        return node

    result = deepcopy(raw)
    result['questions'] = []
    for question in questions:
        fields = {}
        source = visit(question, (), fields)
        segments = source.get('text_segments') if isinstance(source, dict) else None
        if segments and isinstance(segments, list) and all(isinstance(s, dict) and isinstance(s.get('text'), str) for s in segments):
            source['text'] = ''.join(s['text'] for s in segments).strip()
        result['questions'].append(source)
        maps.append(fields)
    result['translation'] = {'language': translation['language'], 'text_maps': maps}
    return result
