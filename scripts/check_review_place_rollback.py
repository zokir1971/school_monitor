"""Read-only guard: old application enum cannot read new persisted values."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import asyncio,json
from sqlalchemy import text,bindparam
from app.db.session import engine

NEW_VALUES=('administrative_meeting','scientific_academy_council','class_teacher_meeting','student_self_government')
COLUMNS_SQL="""SELECT ns.nspname AS schema_name, c.relname AS table_name, a.attname AS column_name
FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
JOIN pg_namespace ns ON ns.oid=c.relnamespace
JOIN pg_type t ON t.oid=a.atttypid JOIN pg_namespace tn ON tn.oid=t.typnamespace
WHERE tn.nspname='public' AND t.typname='review_place' AND c.relkind IN ('r','p')
AND a.attnum>0 AND NOT a.attisdropped ORDER BY ns.nspname,c.relname,a.attname"""


def count_statement(dialect,schema,table,column):
    quote=dialect.identifier_preparer.quote
    sql=f'SELECT count(*) FROM {quote(schema)}.{quote(table)} WHERE CAST({quote(column)} AS text) IN :values'
    return text(sql).bindparams(bindparam('values',expanding=True))


async def check(connection):
    columns=(await connection.execute(text(COLUMNS_SQL))).mappings().all()
    if not columns:raise RuntimeError('PostgreSQL review_place columns not found; rollback cannot be verified.')
    used=[]
    for row in columns:
        statement=count_statement(connection.dialect,row['schema_name'],row['table_name'],row['column_name'])
        count=await connection.scalar(statement,{'values':NEW_VALUES})
        if count:used.append(dict(row,rows=count))
    return used


async def main():
    try:
        async with engine.connect()as connection:used=await check(connection)
        if used:
            print(json.dumps({'rollback_allowed':False,'new_review_places_in_use':used},ensure_ascii=False,indent=2))
            print('Rollback blocked: existing records use new review places. Preserve their history and keep the updated application.');return 2
        print('Rollback database check OK: no persisted new review-place values. Database unchanged.');return 0
    finally:await engine.dispose()


if __name__=='__main__':
    try:sys.exit(asyncio.run(main()))
    except Exception as exc:
        print('Rollback blocked; database check failed:',str(exc));sys.exit(2)
