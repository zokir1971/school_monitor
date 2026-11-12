"""Global objective reference SQL; caller owns transactions."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from sqlalchemy import Table, select, func, or_, and_, update, inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstanceState
from sqlalchemy.sql.elements import ColumnElement

from app.modules.assessment.models import LearningObjective
from app.modules.assessment.models_learning_objective_reference import (
    LearningObjectiveQuarter,
    LearningObjectiveProgram,
)
from app.modules.education.models import Subject


def _column(table: Table, name: str) -> ColumnElement[Any]:
    """Give the IDE a SQL expression type instead of a dynamic .c attribute."""
    return cast(ColumnElement[Any], table.c[name])


class LearningObjectiveReferenceRepo:
    @staticmethod
    def filters(
        *,
        subject_id: int | None = None,
        grade: int | None = None,
        quarter: int | None = None,
        track: str = '',
        state: str = 'all',
        query: str = '',
    ) -> list[ColumnElement[bool]]:
        table = cast(Table, LearningObjective.__table__)
        clauses: list[ColumnElement[bool]] = []
        if subject_id is not None:
            clauses.append(_column(table, 'subject_id') == subject_id)
        if grade is not None:
            clauses.append(_column(table, 'grade_level') == grade)
        if quarter is not None:
            quarters = cast(Table, LearningObjectiveQuarter.__table__)
            clauses.append(
                select(_column(quarters, 'learning_objective_id')).where(
                    _column(quarters, 'learning_objective_id') == _column(table, 'id'),
                    _column(quarters, 'quarter') == quarter,
                ).exists()
            )
        if track:
            clauses.append(_column(table, 'education_track') == track)
        if state != 'all':
            clauses.append(_column(table, 'is_active').is_(state == 'active'))
        if query:
            escaped = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            clauses.append(or_(
                _column(table, 'code').ilike('%' + escaped + '%', escape='\\'),
                _column(table, 'title_kz').ilike('%' + escaped + '%', escape='\\'),
                _column(table, 'title_ru').ilike('%' + escaped + '%', escape='\\'),
            ))
        return clauses

    @staticmethod
    async def subjects(db: AsyncSession) -> list[dict[str, Any]]:
        table = cast(Table, Subject.__table__)
        result = await db.execute(
            select(_column(table, 'id'), _column(table, 'name_kz')).order_by(
                _column(table, 'sort_order'), _column(table, 'name_kz'), _column(table, 'id'),
            )
        )
        return [dict(row) for row in result.mappings()]

    @staticmethod
    async def count(db: AsyncSession, **filters: Any) -> int:
        table = cast(Table, LearningObjective.__table__)
        value = await db.scalar(
            select(func.count()).select_from(table).where(
                *LearningObjectiveReferenceRepo.filters(**filters)
            )
        )
        return int(value or 0)

    @staticmethod
    async def rows(
        db: AsyncSession, *, offset: int, limit: int, **filters: Any,
    ) -> list[dict[str, Any]]:
        table = cast(Table, LearningObjective.__table__)
        subjects = cast(Table, Subject.__table__)
        result = await db.execute(
            select(
                _column(table, 'id'), _column(table, 'code'),
                _column(table, 'grade_level'), _column(table, 'education_track'),
                _column(table, 'title_kz'), _column(table, 'title_ru'),
                _column(table, 'is_active'), _column(table, 'program_id'),
                _column(subjects, 'name_kz').label('subject_name'),
            ).select_from(
                table.join(subjects, _column(table, 'subject_id') == _column(subjects, 'id'))
            ).where(
                *LearningObjectiveReferenceRepo.filters(**filters)
            ).order_by(
                _column(subjects, 'name_kz'), _column(table, 'grade_level'),
                _column(table, 'code'), _column(table, 'id'),
            ).offset(offset).limit(limit)
        )
        return [dict(row) for row in result.mappings()]

    @staticmethod
    async def get(
        db: AsyncSession, objective_id: int, *, lock: bool = False,
    ) -> dict[str, Any] | None:
        table = cast(Table, LearningObjective.__table__)
        columns = [_column(table, name) for name in table.c.keys()]
        statement = select(*columns).where(_column(table, 'id') == objective_id)
        if lock:
            statement = statement.with_for_update()
        row = (await db.execute(statement)).mappings().first()
        if row is None:
            return None
        value: dict[str, Any] = dict(row)
        quarters = cast(Table, LearningObjectiveQuarter.__table__)
        selected_quarters = await db.scalars(
            select(_column(quarters, 'quarter')).where(
                _column(quarters, 'learning_objective_id') == objective_id
            ).order_by(_column(quarters, 'quarter'))
        )
        value['quarters'] = list(selected_quarters.all()) or [value['quarter']]
        return value

    @staticmethod
    async def context(db: AsyncSession, row: Mapping[str, Any]) -> dict[str, Any]:
        subjects = cast(Table, Subject.__table__)
        programs = cast(Table, LearningObjectiveProgram.__table__)
        result = await db.execute(
            select(
                _column(subjects, 'name_kz').label('subject_name'),
                _column(programs, 'title_kz').label('program_title'),
            ).select_from(
                subjects.outerjoin(programs, and_(
                    _column(programs, 'id') == row['program_id'],
                    _column(programs, 'subject_id') == _column(subjects, 'id'),
                ))
            ).where(_column(subjects, 'id') == row['subject_id'])
        )
        return dict(result.mappings().one())

    @staticmethod
    async def update(
        db: AsyncSession, objective_id: int, values: Mapping[str, Any],
    ) -> None:
        table = cast(Table, LearningObjective.__table__)
        await db.execute(
            update(table).where(_column(table, 'id') == objective_id).values(
                **dict(values), updated_at=func.now(),
            )
        )

    @staticmethod
    async def refresh_user(db: AsyncSession, user: Any) -> None:
        state = cast(InstanceState[Any] | None, inspect(user, raiseerr=False))
        if state is not None and state.session is db.sync_session:
            await db.refresh(user)
