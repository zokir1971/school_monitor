"""Batch writes for table imports; caller owns the transaction."""

from __future__ import annotations
from datetime import datetime
import hashlib
import json
from typing import Any
from typing import cast
from sqlalchemy import Table, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assessment.models import LearningObjective, QuestionBankItem
from app.modules.assessment.models_learning_objective_reference import (
    LearningObjectiveQuarter, LearningObjectiveFormulation,
    LearningObjectiveProgram, LearningObjectiveSource,
)
from app.modules.assessment.repositories.learning_objective_import_repo import (
    LearningObjectiveImportRepo,
)


class LearningObjectiveTableImportRepo(LearningObjectiveImportRepo):
    @staticmethod
    async def find_repeat_program(db: AsyncSession, *, meta):
        """One query; file hashes do not define the curriculum identity."""
        pc = cast(Table, LearningObjectiveProgram.__table__).c
        sc = cast(Table, LearningObjectiveSource.__table__).c
        result = await db.execute(
            select(LearningObjectiveProgram, LearningObjectiveSource)
            .join(LearningObjectiveSource, pc.source_id == sc.id)
            .where(
                pc.subject_id == meta["subject_id"],
                pc.appendix_number == meta["appendix_number"],
                pc.variant_key == meta["variant_key"],
                pc.grade_from == meta["grade_from"],
                pc.grade_to == meta["grade_to"],
                pc.education_track == (meta["education_track"] or None),
                pc.instruction_language == (meta["instruction_language"] or None),
                sc.order_number == meta["order_number"],
                sc.order_date == datetime.fromisoformat(meta["order_date"]).date(),
                sc.edition_date == datetime.fromisoformat(meta["edition_date"]).date(),
            )
        )
        candidates = result.all()
        if len(candidates) > 1:
            raise ValueError("Найдено несколько программ с одинаковыми реквизитами. Проверьте справочник программ.")
        return candidates[0] if candidates else None

    @staticmethod
    async def save_table_batch(
        db: AsyncSession,
        *,
        draft,
        objective_values,
        additional_quarters,
        payload,
        result,
        formulations=None,
        existing_objectives=None,
    ):
        objects = [LearningObjective(**values) for values in objective_values]
        db.add_all(objects)
        await db.flush()  # IDs for the whole batch; legacy trigger supplies the first quarter.
        links = [
            {"learning_objective_id": o.id, "quarter": q}
            for o in objects
            for q in payload["quarter_map"][o.code]
            if q != o.quarter
        ]
        links.extend(additional_quarters)
        if links:
            columns = cast(Table, LearningObjectiveQuarter.__table__).c
            await db.execute(
                insert(LearningObjectiveQuarter)
                .values(links)
                .on_conflict_do_nothing(
                    index_elements=[columns.learning_objective_id, columns.quarter]
                )
            )
        if formulations:
            objective_ids = {o.code: o.id for o in objects}
            objective_ids.update({obj.code: obj.id for obj in (existing_objectives or {}).values()})
            await LearningObjectiveTableImportRepo.save_formulations(db, objective_ids=objective_ids, formulations=formulations)
        draft.payload = {
            key: value for key, value in payload.items() if key != "quarter_map"
        }
        draft.result = result
        draft.confirmed_at = datetime.now().astimezone()
        await db.flush()

    @staticmethod
    async def save_formulations(db: AsyncSession, *, objective_ids, formulations) -> None:
        table = cast(Table, LearningObjectiveFormulation.__table__)
        found = await db.execute(select(table).where(table.c.learning_objective_id.in_(list(objective_ids.values()))))
        existing = {(row['learning_objective_id'], row['language'], row['content_key']): dict(row) for row in found.mappings()}
        pending: dict[tuple, dict[str, Any]] = {}
        for code, forms in formulations.items():
            for form in forms:
                content_key = hashlib.sha256(json.dumps(form['source_text'] or [form['title'], form['segments']], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                key = (objective_ids[code], form['language'], content_key)
                target = pending.setdefault(key, {**form, 'learning_objective_id': objective_ids[code], 'content_key': content_key})
                target['quarters'] = sorted(set(target['quarters'] + form['quarters']))
                cells = target['source_cells'] + form['source_cells']
                target['source_cells'] = [json.loads(value) for value in dict.fromkeys(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in cells)]
        inserts = []
        updates = []
        for key, values in pending.items():
            old = existing.get(key)
            if old is None:
                inserts.append(values)
            else:
                quarters = sorted(set(old['quarters'] + values['quarters']))
                cells = [json.loads(value) for value in dict.fromkeys(json.dumps(c, ensure_ascii=False, sort_keys=True) for c in old['source_cells'] + values['source_cells'])]
                updates.append({'id': old['id'], 'quarters': quarters, 'source_cells': cells})
        if inserts:
            await db.execute(insert(LearningObjectiveFormulation), inserts)
        if updates:
            # ORM bulk UPDATE is executed as one batch, with no per-row awaits.
            await db.execute(update(LearningObjectiveFormulation), updates)

    @staticmethod
    async def formulation_text(db: AsyncSession, *, objective_id: int, quarter: int, language: str) -> str | None:
        from app.modules.assessment.repositories.learning_objective_formulation_repo import LearningObjectiveFormulationRepo
        data = await LearningObjectiveFormulationRepo.for_objectives(db, objective_ids=[objective_id])
        forms = data.get(objective_id, [])
        if not forms:
            return None  # Legacy objective without imported formulations.
        return LearningObjectiveFormulationRepo.display(forms, quarter=quarter, language=language)[0] or ''

    @staticmethod
    async def assign_item_quarter(
        db: AsyncSession, *, item_ids: list[int], quarter: int
    ) -> None:
        if type(quarter) is not int or not 1 <= quarter <= 4:
            raise ValueError("Некорректная четверть задания.")
        if not item_ids:
            return
        columns = cast(Table, QuestionBankItem.__table__).c
        await db.execute(
            update(QuestionBankItem)
            .where(columns.id.in_(item_ids))
            .values(quarter=quarter)
        )

    @staticmethod
    async def objective_ids_in_quarter(
        db: AsyncSession, *, objective_ids: list[int], quarter: int
    ) -> set[int]:
        if not objective_ids:
            return set()
        columns = cast(Table, LearningObjectiveQuarter.__table__).c
        result = await db.scalars(
            select(columns.learning_objective_id).where(
                columns.learning_objective_id.in_(objective_ids),
                columns.quarter == quarter,
            )
        )
        return set(result)
