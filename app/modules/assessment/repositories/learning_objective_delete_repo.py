"""Bulk objective deletion. PostgreSQL; caller owns commit/rollback."""
from __future__ import annotations

from typing import Any, cast

from sqlalchemy import Table
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import FromClause
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete, select, text, func, table as sql_table, column, literal, union_all
from app.modules.assessment.models import LearningObjective
from app.modules.assessment.models_learning_objective_reference import (
    LearningObjectiveProgram, LearningObjectiveQuarter, LearningObjectiveFormulation,
)
from app.modules.education.models import Subject


def _column(table: FromClause, name: str) -> ColumnElement[Any]:
    return cast(ColumnElement[Any], table.c[name])


class LearningObjectiveDeleteRepo:
    @staticmethod
    async def subject(db: AsyncSession, subject_id: int):
        return (await db.execute(select(Subject.id, Subject.name_kz).where(
            Subject.id == subject_id))).mappings().first()

    @staticmethod
    async def languages(db: AsyncSession, subject_id: int) -> list[str]:
        program = cast(Table, LearningObjectiveProgram.__table__)
        language = _column(program, 'instruction_language')

        result = await db.scalars(
            select(func.lower(func.trim(language)))
            .where(
                _column(program, 'subject_id') == subject_id,
                language.is_not(None),
            )
            .distinct()
        )

        return sorted(value for value in result.all() if value)

    @staticmethod
    def scope(
        subject_id: int, grade: int | None = None, instruction_language: str = '',
    ) -> list[ColumnElement[bool]]:
        objective = cast(Table, LearningObjective.__table__)
        program = cast(Table, LearningObjectiveProgram.__table__)
        clauses: list[ColumnElement[bool]] = [_column(objective, 'subject_id') == subject_id]
        if grade is not None:
            clauses.append(_column(objective, 'grade_level') == grade)
        language = func.lower(func.trim(_column(program, 'instruction_language')))
        if instruction_language == '__unspecified__':
            # Includes legacy objectives without a program and programs without a language.
            clauses.append(~select(_column(program, 'id')).where(
                _column(program, 'id') == _column(objective, 'program_id'),
                func.coalesce(language, '') != '',
            ).exists())
        elif instruction_language:
            choices = ['uz', 'ug', 'tg', 'uz_ug_tg'] if instruction_language == 'uz_ug_tg' else [instruction_language]
            clauses.append(select(_column(program, 'id')).where(
                _column(program, 'id') == _column(objective, 'program_id'),
                language.in_(choices),
            ).exists())
        return clauses

    @staticmethod
    async def rows(
        db: AsyncSession, *, subject_id: int, grade: int | None = None,
        instruction_language: str = '', lock: bool = False,
    ) -> list[dict[str, Any]]:
        table = cast(Table, LearningObjective.__table__)
        if lock:
            # Prevent new matching rows between the scope check and deletion.
            # Kept only for the short confirmation transaction, never while reading a preview.
            await db.execute(text('LOCK TABLE learning_objectives IN SHARE ROW EXCLUSIVE MODE'))
        stmt = select(_column(table, 'id'), _column(table, 'code'), _column(table, 'grade_level'),
                      _column(table, 'updated_at')).where(
            *LearningObjectiveDeleteRepo.scope(subject_id, grade, instruction_language)
        ).order_by(_column(table, 'id'))
        if lock:
            stmt = stmt.with_for_update()
        return [dict(r) for r in (await db.execute(stmt)).mappings()]

    @staticmethod
    async def references(
        db: AsyncSession, *, subject_id: int, grade: int | None = None,
        instruction_language: str = '',
    ) -> list[dict[str, Any]]:
        # Inspect actual database FKs, including CASCADE/SET NULL links, so deleting
        # an objective cannot silently remove task history or detach a task.
        refs = (await db.execute(text('''
            SELECT ns.nspname AS schema_name, rel.relname AS table_name,
                   attr.attname AS column_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            JOIN LATERAL unnest(con.conkey, con.confkey) AS keys(src, dst) ON true
            JOIN pg_attribute attr ON attr.attrelid = con.conrelid AND attr.attnum = keys.src
            JOIN pg_attribute target ON target.attrelid = con.confrelid AND target.attnum = keys.dst
            WHERE con.contype = 'f' AND con.confrelid = 'learning_objectives'::regclass
              AND target.attname = 'id'
        '''))).mappings().all()
        objective = cast(Table, LearningObjective.__table__)
        own = {
            cast(Table, LearningObjectiveQuarter.__table__).name,
            cast(Table, LearningObjectiveFormulation.__table__).name,
        }
        checks = []
        for ref in refs:
            if ref['table_name'] in own and ref['column_name'] == 'learning_objective_id':
                continue
            remote = sql_table(ref['table_name'], column(ref['column_name']), schema=ref['schema_name'])
            # EXISTS counts distinct referenced objectives, not child rows.
            stmt = select(literal(len(checks)).label('position'), func.count().label('count')).select_from(objective).where(
                *LearningObjectiveDeleteRepo.scope(subject_id, grade, instruction_language),
                select(_column(remote, str(ref['column_name']))).where(
                    _column(remote, str(ref['column_name'])) == _column(objective, 'id'),
                ).exists(),
            )
            checks.append((ref, stmt))
        blocked: list[dict[str, Any]] = []
        for start in range(0, len(checks), 100):
            counts = union_all(*(stmt for _, stmt in checks[start:start + 100])).subquery()
            rows = (await db.execute(select(counts.c.position, counts.c.count)
                                     .order_by(counts.c.position))).all()
            for position, count in rows:
                if count:
                    blocked.append({'table': checks[position][0]['table_name'], 'count': int(count)})
        return blocked

    @staticmethod
    async def remove(
        db: AsyncSession, *, subject_id: int, grade: int | None = None,
        instruction_language: str = '',
    ) -> int:
        table = cast(Table, LearningObjective.__table__)
        ids = select(_column(table, 'id')).where(*LearningObjectiveDeleteRepo.scope(subject_id, grade,
                                                                                    instruction_language))
        for model in (LearningObjectiveFormulation, LearningObjectiveQuarter):
            child = cast(Table, model.__table__)
            await db.execute(delete(child).where(_column(child, 'learning_objective_id').in_(ids)))
        result = await db.execute(delete(table).where(
            *LearningObjectiveDeleteRepo.scope(subject_id, grade, instruction_language)
        ).returning(_column(table, 'id')))
        return len(result.scalars().all())
