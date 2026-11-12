"""Shared explicit work selection for overview pages and Excel; no scoring."""
from app.core.ui_locale_context import ui_locale
from app.modules.assessment.repositories.knowledge_quality_analytics_repo import KnowledgeQualityAnalyticsRepo

CHECKPOINTS = (
    ('', 'Все контрольные точки', 'Барлық бақылау нүктелері'),
    ('baseline', 'Нулевой контроль', 'Нөлдік бақылау'),
    ('quarter_1', 'I четверть', 'I тоқсан'),
    ('quarter_2', 'II четверть', 'II тоқсан'),
    ('quarter_3', 'III четверть', 'III тоқсан'),
    ('quarter_4', 'IV четверть', 'IV тоқсан'),
    ('final', 'Годовой итоговый контроль', 'Жылдық қорытынды бақылау'),
    ('other', 'Другие работы', 'Басқа жұмыстар'),
)

def normalize_filters(options, year, subject, grade):
    year = (options.academic_years[0] if options.academic_years else None) if year is None else year
    return (year if year in options.academic_years else None,
            subject if subject in options.subject_ids else None,
            grade if grade in options.grade_levels else None)

async def prepare_work_selection(db, *, scope, scope_id, academic_year_start,
                                 subject_id=None, grade_level=None, teacher_staff_member_id=None,
                                 work_key='', checkpoint='', search=''):
    kk = ui_locale.get() == 'kk'
    checkpoint = checkpoint if checkpoint in {row[0] for row in CHECKPOINTS} else 'invalid'
    search = search.strip()[:100]
    # Never pass an invalid PostgreSQL enum literal to the query.
    rows = [] if checkpoint == 'invalid' else await KnowledgeQualityAnalyticsRepo.get_work_choices(
        db, scope=scope, scope_id=scope_id, teacher_staff_member_id=teacher_staff_member_id,
        academic_year_start=academic_year_start, subject_id=subject_id, grade_level=grade_level,
        checkpoint=checkpoint, search=search)
    truncated = len(rows) > 200
    choices = []
    for row in rows[:200]:
        number = int(row['logical_id'])
        key = ('d:' + str(number)) if number > 0 else ('a:' + str(-number))
        suffix = (('Сессия' if kk else 'Сессия') + ' №' + str(row['session_id'])) if number > 0 else (('Жұмыс' if kk else 'Работа') + ' №' + str(-number))
        choices.append(dict(row, key=key, label=(row['title'] or '—') + ' · ' + suffix))
    selected = next((row for row in choices if row['key'] == work_key), None)
    if not work_key and len(choices) == 1 and not truncated:
        selected = choices[0]
    if work_key == 'all' and checkpoint != 'invalid':
        selected = dict(key='all', label='Барлық жұмыстар' if kk else 'Все работы')
    prompt = ('Бақылау нүктесін және нақты бағалау жұмысын таңдаңыз. Әртүрлі жұмыстардың нәтижелері қосылмайды.' if kk else
              'Выберите контрольную точку и конкретную оценочную работу. Результаты разных работ не суммируются.')
    return dict(choices=choices, selected=selected, work_key=selected['key'] if selected else 'none',
                checkpoint=checkpoint, search=search, truncated=truncated, prompt=prompt,
                checkpoints=[dict(key=key, label=kz if kk else ru) for key,ru,kz in CHECKPOINTS])
