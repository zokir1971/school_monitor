"""Validated, frozen per-class notebook results. No client totals are trusted."""
from datetime import datetime
from .checking_notebooks import calculate_max_score, calculate_level

CONFLICT_MESSAGE = 'Черновик отчёта обновлён. Изменения не сохранены. Проверьте актуальные данные и повторите действие.'


class NotebookDraftConflict(ValueError):
    def __init__(self):
        super().__init__(CONFLICT_MESSAGE)


MESSAGES = {
    CONFLICT_MESSAGE: 'Есеп жобасы жаңартылды. Өзгерістер сақталмады. Ағымдағы деректерді тексеріп, әрекетті қайталаңыз.',

    'Выберите классы одного предмета из нагрузки учителя.': 'Мұғалімнің жүктемесінен бір пәннің сыныптарын таңдаңыз.',
    'Класс недоступен: проверьте нагрузку учителя и область задачи.': 'Сынып қолжетімсіз: мұғалімнің жүктемесін және тапсырма ауқымын тексеріңіз.',
    'Укажите дату проверки тетрадей.': 'Дәптерлерді тексеру күнін көрсетіңіз.',
    'Заполните количество учеников целыми неотрицательными числами.': 'Оқушылар санын теріс емес бүтін сандармен толтырыңыз.',
    'Есть и нет тетрадей: сумма не должна превышать численность класса.': 'Дәптері бар және жоқ оқушылардың қосындысы сыныптағы оқушылар санынан аспауы тиіс.',
    'Оцените каждый критерий выбранных классов по шкале шаблона.': 'Таңдалған сыныптардың әрбір критерийін үлгі шкаласы бойынша бағалаңыз.',
    'Сократите примечание класса до 2000 символов.': 'Сынып ескертпесін 2000 таңбаға дейін қысқартыңыз.',
    'Список классов изменён в другой вкладке. Обновите отчёт.': 'Сыныптар тізімі басқа қойындыда өзгертілді. Есепті жаңартыңыз.',
    'Уточните область проверки тетрадей.': 'Дәптерлерді тексеру ауқымын нақтылаңыз.',
}


def check_date(raw):
    try:
        return datetime.fromisoformat(str(raw)).date()
    except (ValueError, TypeError):
        raise ValueError('Укажите дату проверки тетрадей.') from None


def criteria_keys(criteria, scale):
    result = []
    for i, item in enumerate(criteria):
        key = str(item.get('key') or f'criterion_{i}') if isinstance(item, dict) else f'criterion_{i}'
        values = (item.get('scores') if isinstance(item, dict) else None) or scale
        values = values.keys() if isinstance(values, dict) else values
        result.append((key, {int(v) for v in values}))
    return result


def snapshot(form, options, schema, *, complete):
    selected = form.getlist('notebook_class')
    if not selected or len(selected) != len(set(selected)) or len(selected) > 100:
        raise ValueError('Выберите классы одного предмета из нагрузки учителя.')
    pool = {row['key']: row for row in options}
    if any(key not in pool for key in selected):
        raise ValueError('Класс недоступен: проверьте нагрузку учителя и область задачи.')
    subject_ids = {pool[key]['subject_id'] for key in selected}
    if len(subject_ids) != 1:
        raise ValueError('Выберите классы одного предмета из нагрузки учителя.')
    criteria = criteria_keys(schema.get('criteria') or [], schema.get('score_scale') or [0, 1, 2])
    maximum = calculate_max_score(criteria=schema.get('criteria') or [], score_scale=schema.get('score_scale') or [0, 1, 2])
    rows = []
    for option in options:
        key = option['key']
        if key not in selected:
            continue
        counts = []
        for field in ('have', 'missing'):
            raw = str(form.get(f'nb_{key}_{field}', '')).strip()
            if not raw and not complete:
                counts.append(None)
            elif len(raw) > 9 or not raw.isascii() or not raw.isdigit():
                raise ValueError('Заполните количество учеников целыми неотрицательными числами.')
            else:
                counts.append(int(raw))
        have, missing = counts
        checked = have + missing if None not in counts else None
        if any(v is not None and v > option['students'] for v in counts) or (checked is not None and checked > option['students']):
            raise ValueError('Есть и нет тетрадей: сумма не должна превышать численность класса.')
        scores = {}
        for criterion, allowed in criteria:
            raw = str(form.get(f'nb_{key}_score_{criterion}', '')).strip()
            if raw == '' and not complete:
                continue
            try:
                value = int(raw)
            except ValueError:
                raise ValueError('Оцените каждый критерий выбранных классов по шкале шаблона.') from None
            if value not in allowed:
                raise ValueError('Оцените каждый критерий выбранных классов по шкале шаблона.')
            scores[criterion] = value
        note = str(form.get(f'nb_{key}_note', '')).strip()
        if len(note) > 2000:
            raise ValueError('Сократите примечание класса до 2000 символов.')
        total = sum(scores.values())
        percent = round(total * 100 / maximum) if maximum else 0
        rows.append(dict(option, have=have, missing=missing, checked=checked,
            unchecked=option['students'] - checked if checked is not None else None,
            scores=scores, total_score=total, max_score=maximum, percent=percent,
            level=calculate_level(percent, rating=schema.get('rating')), note=note))
    totals = {key: sum(r[key] for r in rows) if all(r[key] is not None for r in rows) else None
              for key in ('students', 'have', 'missing', 'checked', 'unchecked', 'total_score', 'max_score')}
    return rows, totals


def revision(report):
    import hashlib
    import json
    if report is None:
        return ''
    data = report.rows_json if isinstance(report.rows_json, dict) else {}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
