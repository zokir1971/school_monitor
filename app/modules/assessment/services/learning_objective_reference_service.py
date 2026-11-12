"""Saved objective editing; no SQL, inserts, deletions or transaction ownership."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assessment.repositories.learning_objective_reference_repo import LearningObjectiveReferenceRepo as Repo
from app.modules.assessment.helpers.learning_objective_rich_contract import validate_rich_row


class ObjectiveNotFound(ValueError):
    pass


class ObjectiveEditConflict(ValueError):
    pass


def version(row): return row['updated_at'].isoformat()


def rich_values(raw):
    if not isinstance(raw, dict):
        raise ValueError('Неверный формат цели.')
    allowed = {key + '_' + lang for key in ('title', 'title_segments', 'has_formula', 'formula_reviewed') for lang in
               ('kz', 'ru')} | {'is_active'}
    if set(raw) - allowed:
        raise ValueError('Предмет, код, класс, направление и четверти менять нельзя.')
    if type(raw.get('is_active')) is not bool:
        raise ValueError('Некорректная активность цели.')
    result = validate_rich_row(raw, label='Учебная цель')
    result['title_ru'] = result['title_ru'] or None
    result['is_active'] = raw['is_active']
    return result


class LearningObjectiveReferenceService:
    @staticmethod
    async def page(db: AsyncSession, *, subject_id=None, grade=None, quarter=None, track='', state='all', query='',
                   page=1):
        if subject_id is not None and subject_id < 1:
            raise ValueError('Неверный предмет.')
        if grade is not None and not 1 <= grade <= 12:
            raise ValueError('Неверный класс.')
        if quarter is not None and not 1 <= quarter <= 4:
            raise ValueError('Неверная четверть.')
        if track not in ('', 'emn', 'ogn') or state not in ('all', 'active', 'inactive'):
            raise ValueError('Неверный фильтр.')
        query = query.strip()
        if len(query) > 200 or page < 1:
            raise ValueError('Неверные параметры списка.')
        filters = dict(subject_id=subject_id, grade=grade, quarter=quarter, track=track, state=state, query=query)
        total = await Repo.count(db, **filters)
        pages = max(1, (total + 24) // 25)
        page = min(page, pages)
        rows = await Repo.rows(db, offset=(page - 1) * 25, limit=25, **filters)
        return dict(rows=rows, total=total, pages=pages, page=page, filters=filters)

    @staticmethod
    async def get(db: AsyncSession, objective_id: int):
        row = await Repo.get(db, objective_id)
        if row is None:
            raise ObjectiveNotFound('Учебная цель не найдена.')
        row.update(await Repo.context(db, row))
        row['version'] = version(row)
        from app.modules.assessment.repositories.learning_objective_formulation_repo import LearningObjectiveFormulationRepo
        row['formulations'] = (await LearningObjectiveFormulationRepo.for_objectives(db, objective_ids=[objective_id])).get(objective_id, [])
        # Legacy rows contain only plain text; hydrate without replacing it.
        for lang in ('kz', 'ru'):
            if not row['title_segments_' + lang]:
                text = row['title_' + lang] or ''
                row['title_segments_' + lang] = [{'type': 'text', 'text': text}] if text else []
        return row

    @staticmethod
    async def update(db: AsyncSession, objective_id: int, *, raw, expected_version: str):
        values = rich_values(raw)
        row = await Repo.get(db, objective_id, lock=True)
        if row is None:
            raise ObjectiveNotFound('Учебная цель не найдена.')
        if not expected_version or version(row) != expected_version:
            raise ObjectiveEditConflict(
                'Цель уже изменена другим пользователем. Откройте страницу заново; ваши изменения не сохранены.')
        from app.modules.assessment.repositories.learning_objective_formulation_repo import LearningObjectiveFormulationRepo
        forms = await LearningObjectiveFormulationRepo.for_objectives(db, objective_ids=[objective_id])
        saved_forms = forms.get(objective_id, [])
        changed_text = any(values.get(key) != row.get(key) for key in values if key != 'is_active')
        if saved_forms and changed_text:
            if any(sum(form['language'] == language for form in saved_forms) > 1 for language in ('kz', 'ru')):
                raise ValueError('Эта цель имеет несколько формулировок. Откройте редактор формулировок; общий редактор не может определить, какую из них менять.')
            updates = []
            for form in saved_forms:
                language = form['language']
                metadata = dict(form['metadata_json'])
                for field in ('has_formula', 'formula_reviewed'):
                    metadata[field + '_' + language] = values[field + '_' + language]
                updates.append({'id': form['id'], 'title': values['title_' + language] or '',
                                'segments': values['title_segments_' + language], 'metadata_json': metadata})
            await LearningObjectiveFormulationRepo.update_texts(db, updates=updates)
        await Repo.update(db, objective_id, values)

    @staticmethod
    async def formulations_page(db: AsyncSession, objective_id: int):
        from app.modules.assessment.repositories.learning_objective_formulation_repo import LearningObjectiveFormulationRepo
        row = await LearningObjectiveReferenceService.get(db, objective_id)
        data = {objective_id: row['formulations']}
        rows = []
        sources = []
        for form in data.get(objective_id, []):
            language = form['language']
            item = {'import_row_id': str(form['id']), 'code': row['code'], 'grade_level': row['grade_level'],
                    'quarters': form['quarters'], **form['metadata_json'],
                    'title_' + language: form['title'], 'title_segments_' + language: form['segments'],
                    'source_cells_' + language: form['source_cells']}
            rows.append(item)
            sources.append({**item, 'quarters': form['metadata_json'].get('source_quarters', form['quarters']),
                            'title_' + language: form['source_text']})
        if not rows:
            raise ValueError('Для этой цели отдельные формулировки ещё не импортированы.')
        return row, rows, sources

    @staticmethod
    async def update_formulations(db: AsyncSession, objective_id: int, *, rows, expected_version: str):
        from app.modules.assessment.services.learning_objective_table_import_service import validate_rows
        from app.modules.assessment.repositories.learning_objective_formulation_repo import LearningObjectiveFormulationRepo
        row = await Repo.get(db, objective_id, lock=True)
        if row is None:
            raise ObjectiveNotFound('Учебная цель не найдена.')
        if not expected_version or version(row) != expected_version:
            raise ObjectiveEditConflict('Цель изменена другим пользователем. Обновите страницу.')
        _, _, sources = await LearningObjectiveReferenceService.formulations_page(db, objective_id)
        validated = validate_rows(rows, meta={'grade_from':row['grade_level'], 'grade_to':row['grade_level'],
                                              'education_track':row['education_track']}, payload={'rows':sources})
        if len(validated) != 1 or validated[0]['code'] != row['code']:
            raise ValueError('В редакторе нельзя менять код или добавлять другую цель.')
        values = validated[0]
        used = await LearningObjectiveFormulationRepo.used_quarters(db, objective_id=objective_id)
        if used - set(values['quarters']):
            raise ValueError('Нельзя убрать четверть, использованную существующим заданием.')
        canonical = {key:value for key,value in values.items() if key not in ('formulations','quarters','code','grade_level','education_track')}
        await Repo.update(db, objective_id, canonical)
        await LearningObjectiveFormulationRepo.replace_all(db, objective_id=objective_id, code=row['code'],
                                                          forms=values['formulations'], quarters=values['quarters'])
