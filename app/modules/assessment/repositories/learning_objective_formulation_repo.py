"""Batch reads and pure projection of quarter-specific exact formulations."""
from __future__ import annotations
from typing import Any, cast
from sqlalchemy import Table, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assessment.models_learning_objective_reference import LearningObjectiveFormulation, LearningObjectiveQuarter
from app.modules.assessment.models import QuestionBankItem, QuestionBankItemObjective


class LearningObjectiveFormulationRepo:
    @staticmethod
    async def for_objectives(db: AsyncSession, *, objective_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
        if not objective_ids:
            return {}
        table = cast(Table, LearningObjectiveFormulation.__table__)
        result = await db.execute(select(table).where(table.c.learning_objective_id.in_(objective_ids)).order_by(table.c.id))
        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in result.mappings():
            grouped.setdefault(row['learning_objective_id'], []).append(dict(row))
        return grouped

    @staticmethod
    def display(forms: list[dict[str, Any]], *, quarter: int | None, language: str, quarters: list[int] | None = None) -> tuple[str | None, tuple[dict[str, str], ...]]:
        matching = [form for form in forms if form['language'] == language and (bool(set(form['quarters']).intersection(quarters)) if quarters is not None else (quarter is None or quarter in form['quarters']))]
        if not matching:
            return None, ()
        segments: list[dict[str, str]] = []
        for index, form in enumerate(matching):
            if index:
                segments.append({'type': 'text', 'text': '\n\n'})
            segments.extend(form['segments'])
        return '\n\n'.join(form['title'] for form in matching), tuple(segments)

    @staticmethod
    async def update_texts(db: AsyncSession, *, updates: list[dict[str, Any]]) -> None:
        if updates:
            await db.execute(update(LearningObjectiveFormulation), updates)

    @staticmethod
    async def used_quarters(db: AsyncSession, *, objective_id: int) -> set[int]:
        item = cast(Table, QuestionBankItem.__table__)
        links = cast(Table, QuestionBankItemObjective.__table__)
        result = await db.scalars(select(item.c.quarter).select_from(item.join(links, item.c.id == links.c.question_bank_item_id)).where(links.c.learning_objective_id == objective_id, item.c.quarter.is_not(None)).distinct())
        return set(result)

    @staticmethod
    async def replace_all(db: AsyncSession, *, objective_id: int, code: str, forms: list[dict[str, Any]], quarters: list[int]) -> None:
        from app.modules.assessment.repositories.learning_objective_table_import_repo import LearningObjectiveTableImportRepo
        from sqlalchemy.dialects.postgresql import insert
        forms_table = cast(Table, LearningObjectiveFormulation.__table__)
        quarters_table = cast(Table, LearningObjectiveQuarter.__table__)
        await db.execute(delete(forms_table).where(forms_table.c.learning_objective_id == objective_id))
        await LearningObjectiveTableImportRepo.save_formulations(db, objective_ids={code:objective_id}, formulations={code:forms})
        await db.execute(delete(quarters_table).where(quarters_table.c.learning_objective_id == objective_id, quarters_table.c.quarter.not_in(quarters)))
        await db.execute(insert(LearningObjectiveQuarter).values([{'learning_objective_id':objective_id,'quarter':q} for q in quarters]).on_conflict_do_nothing())
