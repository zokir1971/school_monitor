"""Subject reference business rules; no SQL or transaction control."""
from __future__ import annotations
from dataclasses import replace
from app.modules.education.helpers.curriculum_policy import POLICIES, canonical_role, validate_rule
from app.modules.education.repositories.subject_category_repo import SubjectCategoryRepo
from app.modules.education.repositories.school_scope_repo import SchoolScopeRepo
from app.modules.education.repositories.curriculum_repo import CurriculumRepo
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.education.repositories.subject_reference_repo import SubjectReferenceRepo
from app.modules.education.schemas.subject_reference_dto import (
    CODE_PATTERN, subject_code_from_ru, SubjectReferenceInput, SubjectReferencePage, SubjectReferenceRow,
)


class SubjectNotFound(ValueError):
    pass


def validate_input(data: SubjectReferenceInput, *, creating: bool) -> None:
    if not isinstance(data.code, str) or not data.code or len(data.code) > 100:
        raise ValueError('Заполните код предмета.')
    if creating and (not CODE_PATTERN.fullmatch(data.code) or data.code != data.code.lower()):
        raise ValueError('Используйте код в нижнем регистре: латинские буквы, цифры, дефис и подчёркивание.')
    if not isinstance(data.name_kz, str) or not data.name_kz.strip() or len(data.name_kz) > 255:
        raise ValueError('Название KZ обязательно, максимум 255 символов.')
    if data.name_ru is not None and (not isinstance(data.name_ru, str) or len(data.name_ru) > 255):
        raise ValueError('Название RU: максимум 255 символов.')
    if type(data.sort_order) is not int or not 0 <= data.sort_order <= 100000:
        raise ValueError('Порядок отображения: целое число от 0 до 100000.')
    if type(data.category_id) is not int or data.category_id <= 0:
        raise ValueError('Выберите категорию предмета.')
    if data.curriculum_role not in POLICIES:
        raise ValueError('Выберите правила преподавания.')
    if type(data.is_active) is not bool:
        raise ValueError('Некорректная активность предмета.')


class SubjectReferenceService:
    @staticmethod
    async def list_page(db: AsyncSession, *, query: str = '', state: str = 'all',
                        page: int = 1, page_size: int = 25, category_id: int | None = None) -> SubjectReferencePage:
        query = query.strip()
        if len(query) > 200:
            raise ValueError('Поиск: максимум 200 символов.')
        if state not in ('all', 'active', 'inactive'):
            raise ValueError('Неизвестный фильтр активности.')
        if type(page) is not int or page < 1 or type(page_size) is not int or not 1 <= page_size <= 100:
            raise ValueError('Некорректная страница списка.')
        if category_id is not None and (type(category_id) is not int or category_id < 0):
            raise ValueError('Некорректная категория.')
        total = await SubjectReferenceRepo.count(db, query=query, state=state, category_id=category_id)
        pages = max(1, (total + page_size - 1) // page_size)
        current = min(page, pages)
        rows = await SubjectReferenceRepo.list_page(db, query=query, state=state,
                                                    offset=(current - 1) * page_size, limit=page_size, category_id=category_id)
        return SubjectReferencePage(rows=rows, query=query, state=state, page=current,
                                    pages=pages, total=total, page_size=page_size, category_id=category_id)

    @staticmethod
    async def get(db: AsyncSession, subject_id: int) -> SubjectReferenceRow:
        row = await SubjectReferenceRepo.get(db, subject_id)
        if row is None:
            raise SubjectNotFound('Предмет не найден.')
        return row

    @staticmethod
    async def create(db: AsyncSession, data: SubjectReferenceInput) -> int:
        data = replace(data, code=subject_code_from_ru(data.name_ru))
        validate_input(data, creating=True)
        if await SubjectCategoryRepo.get(db, data.category_id) is None:
            raise ValueError('Категория не найдена.')
        if await SubjectReferenceRepo.code_exists(db, data.code):
            raise ValueError('Предмет с таким кодом уже существует, в том числе среди неактивных.')
        return await SubjectReferenceRepo.create(db, data)

    @staticmethod
    async def update(db: AsyncSession, subject_id: int, data: SubjectReferenceInput) -> None:
        validate_input(data, creating=False)
        await SchoolScopeRepo.lock_import(db, school_id=0)
        current = await SubjectReferenceRepo.get(db, subject_id, lock=True)
        if current is None:
            raise SubjectNotFound('Предмет не найден.')
        if data.code != current.code:
            raise ValueError('Код существующего предмета изменять нельзя.')
        if await SubjectCategoryRepo.get(db, data.category_id) is None:
            raise ValueError('Категория не найдена.')
        rules = [r for r in await CurriculumRepo.rules(db) if r.subject_id == subject_id]
        changed_rules = [r for r in rules if canonical_role(r.subject_role) != data.curriculum_role]
        if changed_rules:
            if not data.apply_policy:
                raise ValueError('Правила преподавания отличаются от сохранённых. Подтвердите применение ко всем правилам предмета.')
            for rule in rules:
                try:
                    validate_rule(rule.instruction_language, rule.grade_level, rule.grade_level,
                                  data.curriculum_role, rule.split_threshold)
                except ValueError as exc:
                    raise ValueError(f'Правило №{rule.id}: {exc}') from exc
            for rule in rules:
                rule.subject_role = data.curriculum_role
            await CurriculumRepo.flush(db)
        await SubjectReferenceRepo.update(db, subject_id, data)
