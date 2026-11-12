"""Delete only unused subjects; do not cascade into school data."""
import hashlib
import json
import secrets
from app.modules.education.repositories.subject_delete_repo import SubjectDeleteRepo as Repo

LABELS = {
    'learning_objectives': 'Учебные цели',
    'learning_objective_programs': 'Учебные программы',
    'curriculum_subject_rules': 'Правила учебного плана',
    'school_class_subjects': 'Предметы классов',
    'question_bank_items': 'Задания банка',
    'assessments': 'Контрольные работы',
}


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


class SubjectDeleteService:
    @staticmethod
    async def preview(db, subject_id: int, *, lock=False):
        if subject_id < 1:
            raise ValueError('Неверный предмет.')
        row = await Repo.get(db, subject_id, lock=lock)
        if row is None:
            raise ValueError('Предмет не найден или уже удалён.')
        blockers = await Repo.references(db, subject_id)
        for item in blockers:
            item['label'] = LABELS.get(item['table'], 'Другие связанные записи')
        return dict(subject=row, blockers=blockers, fingerprint=fingerprint(row))

    @staticmethod
    async def remove(db, subject_id: int, *, expected: str, confirmation: str):
        if confirmation != 'УДАЛИТЬ':
            raise ValueError('Для подтверждения введите УДАЛИТЬ.')
        preview = await SubjectDeleteService.preview(db, subject_id, lock=True)
        if not expected or not secrets.compare_digest(expected, preview['fingerprint']):
            raise ValueError('Предмет изменился. Откройте подтверждение заново.')
        if preview['blockers']:
            raise ValueError('Предмет используется. Удаление запрещено; при необходимости отключите его через '
                             'редактирование.')
        if not await Repo.remove(db, subject_id):
            raise ValueError('Предмет уже удалён. Обновите список.')
