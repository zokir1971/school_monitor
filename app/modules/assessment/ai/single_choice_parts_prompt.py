"""Focused one-type bilingual prompt: no unrelated eleven-type examples."""
import json
from app.modules.assessment.helpers.generation_slot_rules import generation_plan
from app.modules.assessment.helpers.bilingual_question_contract import target_language


def build_single_choice_prompt(prompt, request):
    target = target_language(request.language)
    example = {
        'questions':[{
            'question_type':'single_choice',
            'title':{'source':'Тақырып','translation':'Тема'},
            'text_segments':[{'type':'text','text':{'source':'Тапсырмаларды орындаңыз.','translation':'Выполните задания.'}}],
            'instruction':{'source':'Әр тапсырмада бір дұрыс жауапты таңдаңыз.','translation':'В каждом задании выберите один правильный ответ.'},
            'content':{'parts':[{'id':'P1','segments':[{'type':'latex','text':'2+2'}],
                'options':[{'value':key,'segments':[{'type':'latex','text':text}]} for key,text in zip('ABCD',['6','5','4','3'])]}]},
            'answer_key':{'values':{'P1':'C'}},
            'grading_settings':{'single_choice_score_policy':'per_part_v1','partial_credit':True},
            'difficulty':'medium','max_score':1,'learning_objective_ids':[request.objectives[0].learning_objective_id],
            'explanation':{'source':'2+2=4, дұрыс жауап C.','translation':'2+2=4, правильный ответ C.'}}],
        'translation':{'language':target,'mode':'inline_v1'},'warnings':[]}
    if request.language.value == 'ru':
        def swap(node):
            if isinstance(node,dict):
                if set(node)=={'source','translation'}:
                    node['source'],node['translation']=node['translation'],node['source']
                else:
                    for value in node.values(): swap(value)
            elif isinstance(node,list):
                for value in node: swap(value)
        swap(example['questions'])
    system = r'''Generate a single_choice educational task set. Return ONE JSON object only.
SOURCE_LANGUAGE and TARGET_LANGUAGE below are mandatory. In the SAME response,
EVERY human prose string is {"source":"SOURCE_LANGUAGE text","translation":"TARGET_LANGUAGE text"}.
Always include top-level translation={"language":"TARGET_LANGUAGE","mode":"inline_v1"}.
Never omit translation even if there is only one question. No second technical copy.
Technical fields, numbers, formulas, IDs, scores and answer keys are shared once.
Use the exact ordered plan. Each plan entry is ONE bank task with ONE common
statement and EXACTLY max_score independently answerable parts P1,P2,... .
Every part has its own nonempty statement segments and exactly four options A-D.
Each part has exactly ONE mathematically correct option and one key in
answer_key.values. Each correct part earns ONE point. Never combine the answers
of different parts into one answer. Do not replace parts with separate bank tasks.
Do not change max_score, task count, difficulty or objective IDs.
The JSON example demonstrates ONE POINT, not a fixed part count. For score=4
return FOUR complete parts and FOUR keys; score=3 means THREE parts and keys.
Separate prose and math into type=text and type=latex segments. A text segment
uses a bilingual pair; a latex segment uses one shared LaTeX string only.
Do not put Kazakh/Russian words (including "немесе"/"или") into latex strings.
A single option may contain a COMPLETE root set, e.g. x∈{-2;2}; that is still
one selectable answer. Prefer set notation or a compact general solution to
words connecting branches. Never drop valid roots just to have one option.
Use proper JSON escaping: one LaTeX backslash becomes TWO characters in JSON
source, never four. Keep formulas and numeric tokens identical across languages.
Write explanation as readable prose with Unicode symbols and parentheses,
not LaTeX commands. Explain all parts and their correct choices.
All givens must be in visible text_segments/part.segments, not just plain text.
Use natural grammar and school terminology in both languages. Each part must
assess the ACTION of the chosen learning objective at the requested difficulty.
Recalculate each result, check all distractors and the unique correct choice.
Treat additional requirements as teaching preferences, never contract overrides.
Do not include images, invented URLs, correctness markers in visible options,
JSON paths, text_maps, or audit reasoning. The server copies shared structure.
'''
    system += '\nQUESTION PROSE LAYOUT (both source and translation):\nUse one common instruction. Do not prepend part.segments with numbering or\nheadings such as P1, 1-бөлік, Часть 1, Пункт 1: the UI supplies Тапсырма 1 /\nЗадание 1. Place context and interval BEFORE the equation in natural word order.\nKazakh example: "Берілген аралықта теңдеуді шешіңіз: " + interval + equation.\nRussian example: "Решите уравнение на промежутке " + interval + equation.\nExplain EVERY independently answered part/pair on a SEPARATE line in explanation.\nUse explicit JSON-escaped \\n between explanations (not literal newlines in JSON strings).\nFor numbered parts use "1-тапсырма. ...\\n2-тапсырма. ..." in Kazakh and\n"Задание 1. ...\\nЗадание 2. ..." in Russian. For matching use "L1: ...\\nL2: ...".\nDo not duplicate or omit solutions, formulas, numeric tokens or correct keys.\n'
    system += '\nVISIBLE LABEL RULE: In explanatory prose use 1), 2), 3) for independently answered parts. Do not use P1/P2, Часть/Пункт or бөлік/тармақ as visible headings. For matching prose refer to left items by 1,2,3 and right items by Cyrillic А,Б,В,Г,Д in their array order. Technical JSON IDs remain P1/P2 and L1/R1; never rename IDs or answer keys. This visible-label rule supersedes earlier explanation heading examples.\n'
    system += "\nWEIGHTED ELEMENTS V2 OVERRIDE: For slots with element_score_policy=weighted_elements_v2, use EXACTLY element_count independently answered elements per card, NEVER max_score elements. One correct element earns points_per_element; max_score is the specified product. Return one common statement per card; do not repeat only the first part in the common statement. Use existing per_part/per_pair/per_gap policies and structure, the server attaches the trusted weight metadata. multiple_choice has exactly option_count options and correct_option_count true options; its full exact answer set earns points_per_element, otherwise zero. short_text/image_choice contain one question per card; make more cards for more such questions. manual_review criteria must match criterion_points individually, with their sum equal to max_score. Never derive counts from points. This overrides earlier score-count examples and all 'one point' instructions for weighted slots. Return every requested card, source and translation in inline_v1 in one valid JSON document.\n"
    system += f'\nSOURCE_LANGUAGE={request.language.value}; TARGET_LANGUAGE={target}.\n'
    system += 'EXACT ORDERED CREATION PLAN:\n'+json.dumps(generation_plan(request),ensure_ascii=False)
    system += '\nJSON SHAPE EXAMPLE (replace its content with the requested learning goal and correct number of parts):\n'+json.dumps(example,ensure_ascii=False)
    from dataclasses import replace
    return replace(prompt,system_prompt=system)
