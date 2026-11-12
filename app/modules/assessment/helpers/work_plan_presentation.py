"""One canonical ordering for teacher/pupil previews, printed sheets and rosters."""
import re
from types import SimpleNamespace
from app.modules.assessment.enums import AssessmentQuestionType, AssessmentQuestionDifficulty
from app.modules.assessment.services.bilingual_question_views import localized_view
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError, required_languages

DIFFICULTY = {'basic': 0, 'medium': 1, 'advanced': 2}
TYPE_ORDER = {value.value: index for index, value in enumerate(AssessmentQuestionType)}

def title_for(plan, language):
    return getattr(plan, 'title_' + language, None) or plan.title

def title_values(values, policy):
    result = {lang: str(values.get('title_' + lang, '')).strip() for lang in ('kk', 'ru')}
    if any(len(value) > 255 for value in result.values()):
        raise WorkPlanError('Название на каждом языке должно содержать не более 255 символов.')
    if any(not result[lang] for lang in required_languages(policy)):
        raise WorkPlanError('Заполните названия на всех языках комплекта.')
    return result

def goal_key(goal):
    value = str(goal.get('code', ''))
    if not re.fullmatch(r'\d+(?:\.\d+){3}', value):
        return (1, 0, 0, 0, 0, value)
    grade, section, subsection, number = map(int, value.split('.'))
    return (0, section, subsection, number, grade, '')

def ordered_items(items):
    def key(item):
        goals = tuple(sorted(goal_key(goal) for goal in item.objectives))
        return (goals or ((2, 0, 0, 0, 0, ''),), DIFFICULTY.get(item.difficulty, 99),
                TYPE_ORDER.get(item.question_type, 99), item.order_no, item.id or 0)
    return sorted(items, key=key)

def document_rows(items, language, audience):
    if audience not in ('teacher', 'student'):
        raise WorkPlanError('Выберите учительский или ученический просмотр.')
    rows = []
    for item in ordered_items(items):
        if language not in item.payloads:
            raise WorkPlanError('Нет сохранённой версии на выбранном языке.')
        payload = item.payloads[language]
        if audience == 'student':
            # Never send solutions/criteria/comments to a pupil template, DOM or JS.
            payload = {key: payload.get(key) for key in ('title', 'text', 'text_segments', 'instruction', 'content')}
        view = localized_view(SimpleNamespace(question_type=AssessmentQuestionType(item.question_type),
            difficulty=AssessmentQuestionDifficulty(item.difficulty), max_score=item.max_score), payload, language)
        if audience == 'student':
            view.answer_key = {}; view.grading_settings = {key: payload_value for key, payload_value in item.payloads[language].get('grading_settings', {}).items() if key in ('points_per_element','element_count')}; view.explanation = None; view.author_comment = None
        rows.append(SimpleNamespace(number=len(rows)+1, item=item if audience=='teacher' else None,
            view=view, objectives=sorted(item.objectives, key=goal_key) if audience=='teacher' else [], max_score=item.max_score))
    return rows


def adapt_print_rows(rows, items, response_mode):
    """Exact repetition only; never infer/remove mathematical restrictions."""
    import json
    prompts={
        'Выберите один правильный ответ', 'В каждом задании выберите один правильный ответ',
        'В каждом пункте выберите один правильный ответ', 'Бір дұрыс жауапты таңдаңыз',
        'Әр тапсырмада бір дұрыс жауапты таңдаңыз', 'Әрбір бөлікте бір дұрыс жауапты таңдаңыз',
    }
    previous=None
    for row,source in zip(rows,ordered_items(items)):
        row.repeat_condition=False
        row.print_instruction=row.view.instruction
        if response_mode!='open' or source.question_type!='single_choice':
            previous=None
            continue
        instruction=(row.view.instruction or '').strip().rstrip('.!').strip()
        if instruction in prompts:row.print_instruction=''
        signature=(tuple(sorted(g['id'] for g in source.objectives)),source.question_type,
            json.dumps(row.view.text_segments or row.view.text,ensure_ascii=False,sort_keys=True),row.print_instruction)
        row.repeat_condition=signature==previous
        previous=signature
    return rows
