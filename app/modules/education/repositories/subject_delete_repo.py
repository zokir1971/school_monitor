"""Subject deletion SQL; caller owns transactions. PostgreSQL."""
from __future__ import annotations
from typing import Any, cast
from sqlalchemy import Table, column, delete, func, select, table as sql_table, text, literal, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import FromClause
from app.modules.education.models import Subject


def col(table: FromClause, name: str) -> ColumnElement[Any]:
    return cast(ColumnElement[Any], table.c[name])


class SubjectDeleteRepo:
    @staticmethod
    async def get(db: AsyncSession, subject_id: int, *, lock: bool = False):
        table = cast(Table, Subject.__table__)
        stmt = select(table).where(col(table, 'id') == subject_id)
        if lock:
            stmt = stmt.with_for_update()
        row = (await db.execute(stmt)).mappings().first()
        return dict(row) if row is not None else None

    @staticmethod
    async def references(db: AsyncSession, subject_id: int) -> list[dict[str, Any]]:
        refs = (await db.execute(text('''
            SELECT ns.nspname AS schema_name, rel.relname AS table_name,
                   attr.attname AS column_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            JOIN pg_namespace ns ON ns.oid = rel.relnamespace
            JOIN LATERAL unnest(con.conkey, con.confkey) AS keys(src, dst) ON true
            JOIN pg_attribute attr ON attr.attrelid = con.conrelid AND attr.attnum = keys.src
            JOIN pg_attribute target ON target.attrelid = con.confrelid AND target.attnum = keys.dst
            WHERE con.contype = 'f' AND con.confrelid = 'subjects'::regclass
              AND target.attname = 'id'
        '''))).mappings().all()
        blockers = []
        # Keep dynamic catalog coverage, but count references in bounded batches.
        for start in range(0, len(refs), 100):
            statements = []
            for position, ref in enumerate(refs[start:start + 100], start=start):
                remote = sql_table(str(ref['table_name']), column(str(ref['column_name'])),
                                   schema=str(ref['schema_name']))
                statements.append(select(literal(position).label('position'), func.count().label('count'))
                    .select_from(remote).where(col(remote, str(ref['column_name'])) == subject_id))
            counts = union_all(*statements).subquery()
            rows = (await db.execute(select(counts.c.position, counts.c.count)
                                     .order_by(counts.c.position))).all()
            for position, count in rows:
                if count:
                    blockers.append(dict(table=str(refs[position]['table_name']), count=int(count)))
        return blockers

    @staticmethod
    async def remove(db: AsyncSession, subject_id: int) -> bool:
        table = cast(Table, Subject.__table__)
        result = await db.execute(delete(table).where(col(table, 'id') == subject_id).returning(col(table, 'id')))
        return result.scalar_one_or_none() is not None
