"""Explicit subject/grade/language scope; preview before atomic deletion."""
from __future__ import annotations
import hashlib
import json
import secrets
from app.modules.assessment.repositories.learning_objective_delete_repo import LearningObjectiveDeleteRepo as Repo


LANGUAGE_LABELS = {
    'kz': 'Казахский', 'ru': 'Русский',
    'uz': 'Узбекский', 'ug': 'Уйгурский', 'tg': 'Таджикский',
    'uz_ug_tg': 'Уйгурский / узбекский / таджикский',
    '__unspecified__': 'Язык обучения не указан',
}


def parse_scope(subject_id, grade='', instruction_language=''):
    try:
        scope = dict(subject_id=int(subject_id), grade=int(grade) if grade else None,
                     instruction_language=str(instruction_language or '').strip().lower())
    except (ValueError, TypeError) as error:
        raise ValueError('Выберите предмет, параллель и язык обучения.') from error
    if scope['subject_id'] < 1 or (scope['grade'] is not None and not 1 <= scope['grade'] <= 12):
        raise ValueError('Неверный предмет или параллель.')
    if len(scope['instruction_language']) > 32:
        raise ValueError('Неверный язык обучения.')
    return scope


def language_options(values):
    options = dict(LANGUAGE_LABELS)
    options.update({value: LANGUAGE_LABELS.get(value, value) for value in values})
    return options


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, default=str,
                                     ensure_ascii=False).encode()).hexdigest()


class LearningObjectiveDeleteService:
    @staticmethod
    async def preview(db, scope, *, lock=False):
        subject = await Repo.subject(db, scope['subject_id'])
        if subject is None:
            raise ValueError('Предмет не найден.')
        languages = language_options(await Repo.languages(db, scope['subject_id']))
        selected = scope['instruction_language']
        if selected and selected not in languages:
            raise ValueError('Неверный язык обучения. Откройте предварительный просмотр заново.')
        rows = await Repo.rows(db, **scope, lock=lock)
        return dict(scope=scope, subject=dict(subject), languages=languages,
                    language_label=languages.get(selected, 'Все языки обучения'),
                    count=len(rows), fingerprint=fingerprint(rows),
                    blockers=await Repo.references(db, **scope))

    @staticmethod
    async def remove(db, scope, *, expected, confirmation):
        if confirmation != 'УДАЛИТЬ':
            raise ValueError('Для подтверждения введите УДАЛИТЬ.')
        preview = await LearningObjectiveDeleteService.preview(db, scope, lock=True)
        if not expected or not secrets.compare_digest(expected, preview['fingerprint']):
            raise ValueError('Набор целей изменился. Выполните предварительный просмотр заново.')
        if preview['blockers']:
            raise ValueError('Удаление отменено: цели используются в заданиях или других записях. Ничего не удалено.')
        if not preview['count']:
            raise ValueError('В выбранной области нет учебных целей.')
        count = await Repo.remove(db, **scope)
        if count != preview['count']:
            raise ValueError('Набор целей изменился. Ничего не сохранено; повторите просмотр.')
        return count
