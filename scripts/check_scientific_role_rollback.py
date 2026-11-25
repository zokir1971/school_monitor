"""Read-only guard before reverting source code that knows the new role."""
import asyncio,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text

VALUE='d_scientific_methodical'
COLUMNS_SQL="""SELECT ns.nspname AS schema_name,c.relname AS table_name,a.attname AS column_name,
    a.atttypid=base.typarray AS is_array
FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
JOIN pg_namespace ns ON ns.oid=c.relnamespace
JOIN pg_type base ON (a.atttypid=base.oid OR a.atttypid=base.typarray)
JOIN pg_namespace tn ON tn.oid=base.typnamespace
WHERE tn.nspname='public' AND base.typname='responsible_role_enum'
AND c.relkind IN ('r','p') AND a.attnum>0 AND NOT a.attisdropped
ORDER BY ns.nspname,c.relname,a.attname"""

def statement(dialect,row):
    quote=dialect.identifier_preparer.quote
    col=quote(row['column_name']);table=quote(row['schema_name'])+'.'+quote(row['table_name'])
    predicate=f':new_role = ANY(CAST({col} AS text[]))'if row['is_array']else f'CAST({col} AS text) = :new_role'
    return text(f'SELECT count(*) FROM {table} WHERE {predicate}')

async def check(conn):
    columns=(await conn.execute(text(COLUMNS_SQL))).mappings().all()
    if not columns:raise RuntimeError('Role columns not found; rollback cannot be verified')
    used=[]
    for row in columns:
        count=await conn.scalar(statement(conn.dialect,row),{'new_role':VALUE})
        if count:used.append(dict(row,rows=count))
    return used

async def main():
    from app.db.session import engine
    try:
        async with engine.connect()as conn:used=await check(conn)
        print(json.dumps({'rollback_allowed':not used,'new_role_in_use':used},ensure_ascii=False,indent=2))
        return 2 if used else 0
    finally:await engine.dispose()

if __name__=='__main__':sys.exit(asyncio.run(main()))
