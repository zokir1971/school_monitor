"""Database operations for objective imports; never commit or rollback here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import Table, inspect, select, tuple_, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.assessment.models import LearningObjective
from app.modules.assessment.models_learning_objective_import import (
    LearningObjectiveImportDraft,
)
from app.modules.assessment.models_learning_objective_reference import (
    LearningObjectiveProgram,
    LearningObjectiveQuarter,
    LearningObjectiveSource,
)
from app.modules.education.models import Subject


class LearningObjectiveImportRepo:
    @staticmethod
    async def list_subjects(db: AsyncSession) -> list[dict[str, Any]]:
        columns = cast(Table, Subject.__table__).c
        name_ru = columns.name_ru if "name_ru" in columns else literal(None).label("name_ru")
        result = await db.execute(
            select(columns.id, columns.code, columns.name_kz, name_ru).where(columns.is_active.is_(True))
            .order_by(columns.sort_order, columns.name_kz, columns.id)
        )
        return [dict(row) for row in result.mappings()]

    @staticmethod
    async def get_subject_name(db: AsyncSession, subject_id: int) -> str | None:
        columns = cast(Table, Subject.__table__).c
        return await db.scalar(select(columns.name_kz).where(columns.id == subject_id, columns.is_active.is_(True)))

    @staticmethod
    async def subject_exists(db: AsyncSession, subject_id: int) -> bool:
        columns = cast(Table, Subject.__table__).c
        return (
            await db.scalar(select(columns.id).where(columns.id == subject_id, columns.is_active.is_(True)))
            is not None
        )

    @staticmethod
    async def get_source(
        db: AsyncSession, document_key: str
    ) -> LearningObjectiveSource | None:
        columns = cast(Table, LearningObjectiveSource.__table__).c
        return await db.scalar(
            select(LearningObjectiveSource).where(columns.document_key == document_key)
        )

    @staticmethod
    async def get_program(
        db: AsyncSession,
        *,
        subject_id: int,
        source_id: int,
        appendix_number: str,
        variant_key: str,
    ) -> LearningObjectiveProgram | None:
        columns = cast(Table, LearningObjectiveProgram.__table__).c
        return await db.scalar(
            select(LearningObjectiveProgram).where(
                columns.subject_id == subject_id,
                columns.source_id == source_id,
                columns.appendix_number == appendix_number,
                columns.variant_key == variant_key,
            )
        )

    @staticmethod
    async def load_objectives(
        db: AsyncSession,
        *,
        subject_id: int,
        keys: Sequence[tuple[int, str]],
        education_track: str = "",
        program_id: int | None = None,
    ) -> dict[tuple[int, str], LearningObjective]:
        if not keys:
            return {}
        columns = cast(Table, LearningObjective.__table__).c
        result = await db.scalars(
            select(LearningObjective).where(
                columns.subject_id == subject_id,
                columns.program_id == program_id,
                columns.education_track == education_track,
                tuple_(columns.grade_level, columns.code).in_(keys),
            ).order_by(columns.id).with_for_update()
        )
        return {(item.grade_level, item.code): item for item in result}

    @staticmethod
    async def load_quarters(
        db: AsyncSession, objective_ids: Sequence[int]
    ) -> set[tuple[int, int]]:
        if not objective_ids:
            return set()
        columns = cast(Table, LearningObjectiveQuarter.__table__).c
        result = await db.execute(
            select(columns.learning_objective_id, columns.quarter).where(
                columns.learning_objective_id.in_(objective_ids)
            )
        )
        return {(row[0], row[1]) for row in result}

    @staticmethod
    async def create_source(
        db: AsyncSession, values: Mapping[str, Any]
    ) -> LearningObjectiveSource:
        source = LearningObjectiveSource(**values)
        db.add(source)
        await db.flush()
        return source

    @staticmethod
    async def create_program(
        db: AsyncSession, values: Mapping[str, Any]
    ) -> LearningObjectiveProgram:
        program = LearningObjectiveProgram(**values)
        db.add(program)
        await db.flush()
        return program

    @staticmethod
    async def create_draft(
        db: AsyncSession, values: Mapping[str, Any]
    ) -> LearningObjectiveImportDraft:
        draft = LearningObjectiveImportDraft(**values)
        db.add(draft)
        await db.flush()
        return draft

    @staticmethod
    async def get_owned_draft(
        db: AsyncSession,
        *,
        draft_id: str,
        user_id: int,
        lock: bool = False,
    ) -> LearningObjectiveImportDraft | None:
        columns = cast(Table, LearningObjectiveImportDraft.__table__).c
        query = select(LearningObjectiveImportDraft).where(
            columns.id == draft_id,
            columns.owner_user_id == user_id,
        )
        if lock:
            query = query.with_for_update()
        return await db.scalar(query)

    @staticmethod
    async def save_confirmed_batch(
        db: AsyncSession,
        *,
        draft: LearningObjectiveImportDraft,
        objective_values: Sequence[Mapping[str, Any]],
        payload: dict[str, Any],
        result: dict[str, Any],
        confirmed_at: datetime,
    ) -> None:
        db.add_all([LearningObjective(**values) for values in objective_values])
        draft.payload = payload
        draft.result = result
        draft.confirmed_at = confirmed_at
        # One flush for the entire objective batch and draft. PostgreSQL's existing
        # trigger fills learning_objective_quarters for each inserted objective.
        await db.flush()

    @staticmethod
    async def refresh_user_after_rollback(db: AsyncSession, user: Any) -> None:
        state = inspect(user, raiseerr=False)
        if state is not None and state.session is db.sync_session:
            await db.refresh(user)
