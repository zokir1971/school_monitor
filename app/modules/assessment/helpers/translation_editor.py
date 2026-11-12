"""User-facing groups over the existing protected translation fields.

The renderer edits text only. Formula/media tokens are always sourced from the
original task; the server still reconstructs and validates the same contract.
"""
from copy import deepcopy
from app.modules.assessment.helpers.question_prose_layout import matching_letter
from app.modules.assessment.helpers.bilingual_question_contract import (
    translation_fields, _all_translation_fields, _translation_group, statement_slots)


def field_label(path, source):
    root, last = path[0], path[-1]
    if root in {'title','text','instruction','explanation','author_comment'}:
        return {'title':'Тема','text':'Условие задания','instruction':'Инструкция',
                'explanation':'Пояснение','author_comment':'Комментарий автора'}[root], ''
    indices = [v for v in path if isinstance(v,int)]
    number = str(indices[0]+1) if indices else ''
    if root == 'grading_settings':
        return (('Описание критерия' if last=='description' else 'Критерий оценивания') if 'criteria' in path else 'Описание оценивания'), number
    if root == 'answer_key':
        return ('Допустимый ответ' if 'accepted_answers' in path else 'Текст ответа'), number
    for collection, label in [('options','Вариант ответа'),('statements','Утверждение'),
        ('parts','Часть задания'),('left','Левая часть сопоставления'),
        ('right','Правая часть сопоставления'),('elements','Элемент порядка'),
        ('word_bank','Вариант из банка ответов')]:
        if collection in path:
            detail = number
            at = path.index(collection)
            if at+1 < len(path) and isinstance(path[at+1],int):
                node = source
                try:
                    for key in path[:at+2]:node=node[key]
                    if isinstance(node,dict):
                        index = path[at+1]
                        if collection == 'left':detail=str(index+1)
                        elif collection in ('right', 'word_bank'):detail=matching_letter(index)
                        elif collection == 'parts':detail=f'{index+1})'
                        else:detail=str(node.get('value') or number)
                except (KeyError,IndexError,TypeError):pass
            return label, detail
    return 'Текст задания', number


def build_translation_editor(source, question_type, values):
    source = statement_slots(source)
    fields = translation_fields(source,question_type)
    names = {_translation_group(path,text):f'f{i}' for i,(path,text) in enumerate(fields)}
    paths = {path:names[_translation_group(path,text)] for path,text in _all_translation_fields(source,question_type)}
    groups=[];consumed=set();statement_field=None
    def rich(segments,path,label,detail):
        nonlocal statement_field
        target=[]
        for index,segment in enumerate(segments):
            piece=deepcopy(segment)
            if segment.get('type')=='text':
                name=paths.get(path+(index,'text'))
                if name:
                    piece.update(field=name,text=values.get(name,''));consumed.add(name)
            target.append(piece)
        if path==('text_segments',):
            statement_field=paths.get(('text',));consumed.add(statement_field)
        groups.append(dict(kind='rich',label=label,detail=detail,
            source_segments=deepcopy(segments),target_segments=target,statement_field=statement_field if path==('text_segments',) else None))
    def walk(node,path):
        if isinstance(node,list):
            if node and all(isinstance(s,dict) and s.get('type') in ['text','latex','image'] for s in node):
                label,detail=('Условие задания','') if path==('text_segments',) else field_label(path,source)
                rich(node,path,label,detail);return
            for i,value in enumerate(node):walk(value,path+(i,))
        elif isinstance(node,dict):
            for key,value in node.items():walk(value,path+(key,))
        elif path in paths:
            name=paths[path]
            if name in consumed:return
            label,detail=field_label(path,source)
            groups.append(dict(kind='text',label=label,detail=detail,name=name,
                source=node,value=values.get(name,'')));consumed.add(name)
    # The plain statement is derived from the complete rich statement, never
    # shown a second time as a duplicate editable field.
    for key in ['title','text_segments','text','instruction','content','answer_key','grading_settings','explanation','author_comment']:
        walk(source.get(key),(key,))
    # Alt text and any less common supported human-text field must remain
    # reachable, even when its parent is a protected rich/media group.
    for i,(path,text) in enumerate(fields):
        name=f'f{i}'
        if name in consumed:continue
        label,detail=field_label(path,source)
        if path[-1]=='alt':label='Описание изображения'
        groups.append(dict(kind='text',label=label,detail=detail,name=name,
            source=text,value=values.get(name,'')))
        consumed.add(name)
    return groups
