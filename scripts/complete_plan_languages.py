"""Install all six bilingual directions, with guarded backups and no monthly tasks."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,asyncio,gzip,json,os
from datetime import datetime,date
from enum import Enum
from sqlalchemy import select,update,delete
from app.db.session import async_session_maker,engine
from app.db.base import Base
from app.modules.planning.models import PlanTemplate
from app.modules.planning.models_school import SchoolPlan
from app.modules.planning.content_completion import MODELS,prepare_completion,insert_completion
from app.modules.planning.content_import import prepare_catalog_changes

SCHEMA='planning-six-directions-332'
TABLES={m.__tablename__ for m in MODELS}

def plain(value):
    if isinstance(value,Enum):return value.value
    if isinstance(value,(datetime,date)):return value.isoformat()
    if isinstance(value,dict):return {k:plain(v)for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v)for v in value]
    return value


def snapshot(obj):
    return {c.key:plain(getattr(obj,c.key))for c in obj.__table__.columns if c.key!='created_at'}


def write_backup(path,data,*,replace=False):
    target=path.with_name(path.name+'.pending') if replace else path
    try:
        with target.open('xb')as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb')as stream:
                stream.write(json.dumps(data,ensure_ascii=False).encode('utf-8'))
            raw.flush();os.fsync(raw.fileno())
        if replace:os.replace(target,path)
    finally:
        if replace:target.unlink(missing_ok=True)


async def lock_plans(db,states):
    if not states:return
    ids=[p['id']for p in states]
    rows=(await db.execute(select(SchoolPlan.id,SchoolPlan.template_id,SchoolPlan.academic_year,SchoolPlan.status)
        .where(SchoolPlan.id.in_(ids)).order_by(SchoolPlan.id).with_for_update())).mappings().all()
    if [dict(row)for row in rows]!=states:
        raise RuntimeError('Состояние школьного плана изменилось. Изменения отменены; повторите проверку.')


async def restore(db,backup,apply):
    if backup.get('schema')!=SCHEMA or backup.get('phase')!='ready_to_commit':
        raise RuntimeError('Неподдерживаемая или незавершённая резервная копия.')
    await db.execute(select(PlanTemplate.id).where(PlanTemplate.id==backup['template_id']).with_for_update())
    await lock_plans(db,backup['plans'])
    created={}
    for item in backup['created']:
        if item['table']not in TABLES:raise RuntimeError('Invalid backup table')
        table=Base.metadata.tables[item['table']]
        current=(await db.execute(select(table).where(table.c.id==item['id']).with_for_update())).mappings().one_or_none()
        if current is None or {k:plain(current[k])for k in item['values']}!=item['values']:
            raise RuntimeError('Добавленная строка изменена или отсутствует: '+item['table']+' #'+str(item['id']))
        created.setdefault(item['table'],[]).append(item['id'])
    # Any later assignment/monthly item/document or other FK-dependent data
    # blocks deletion, even if the source row itself was never changed.
    for child in Base.metadata.tables.values():
        for fk in child.foreign_keys:
            parent=fk.column.table.name
            if parent not in created or fk.column.name!='id':continue
            stmt=select(child.c.id).where(fk.parent.in_(created[parent]))
            if child.name in created:stmt=stmt.where(child.c.id.not_in(created[child.name]))
            if await db.scalar(stmt.limit(1))is not None:
                raise RuntimeError('После установки появились связанные данные: '+child.name+'. Откат остановлен.')
    for item in backup['changes']:
        if item['table']not in TABLES:raise RuntimeError('Invalid backup table')
        table=Base.metadata.tables[item['table']]
        current=await db.scalar(select(table.c.text_i18n).where(table.c.id==item['id']).with_for_update())
        if current!=item['after']:raise RuntimeError('Языковая версия изменена после установки. Откат остановлен.')
    for item in backup['updates']:
        if item['table']!='plan_directions' or item['field']!='is_active':raise RuntimeError('Invalid backup field')
        t=Base.metadata.tables[item['table']]
        if await db.scalar(select(t.c.is_active).where(t.c.id==item['id']).with_for_update())!=item['after']:
            raise RuntimeError('Активность направления изменена после установки.')
    if not apply:
        print('RESTORE CHECK OK: database unchanged.');return
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in created:await db.execute(delete(table).where(table.c.id.in_(created[table.name])))
    for item in backup['changes']:
        table=Base.metadata.tables[item['table']]
        await db.execute(update(table).where(table.c.id==item['id']).values(text_i18n=item['before']))
    for item in backup['updates']:
        table=Base.metadata.tables[item['table']]
        await db.execute(update(table).where(table.c.id==item['id']).values({item['field']:item['before']}))
    await db.commit();print('RESTORED: added rows removed; previous language versions restored.')


async def main(args):
    async with async_session_maker()as db:
        db.sync_session.info['planning_i18n_seed']=True
        if args.restore_backup:
            with gzip.open(args.restore_backup,'rt',encoding='utf-8')as stream:backup=json.load(stream)
            await restore(db,backup,args.apply);return
        template=await db.scalar(select(PlanTemplate.id).where(PlanTemplate.id==args.template_id).with_for_update())
        if template is None:raise RuntimeError('Шаблон не найден; проверьте --template-id.')
        report,changes,updates,additions,plans,fills=await prepare_completion(db,template_id=template,academic_year=args.academic_year)
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if not args.apply:
            print('CHECK ONLY: database unchanged. Use --apply to complete all six directions.');return
        if report['completion']['final_catalog_direction_count']!=6:
            raise RuntimeError('Не подтверждены все шесть направлений. База не изменена.')
        if not changes and not updates and not additions:
            print('ALREADY INSTALLED: all six directions present; no changes.');return
        await lock_plans(db,plans)
        folder=Path(args.backup_dir).expanduser();folder.mkdir(parents=True,exist_ok=True)
        path=folder/('school_monitor_six_directions332_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json.gz')
        backup=dict(schema=SCHEMA,phase='prepared',template_id=template,academic_year=args.academic_year,
                    plans=plans,report=report,changes=changes,updates=updates,created=[])
        write_backup(path,backup);print('Backup:',path)
        for item in changes:
            table=Base.metadata.tables[item['table']]
            result=await db.execute(update(table).where(table.c.id==item['id'],table.c.text_i18n==item['before']).values(text_i18n=item['after']))
            if result.rowcount!=1:raise RuntimeError('Обнаружена параллельная правка; транзакция отменена.')
        for item in updates:
            table=Base.metadata.tables[item['table']]
            result=await db.execute(update(table).where(table.c.id==item['id'],table.c[item['field']]==item['before']).values({item['field']:item['after']}))
            if result.rowcount!=1:raise RuntimeError('Направление изменено; транзакция отменена.')
        objects=await insert_completion(db,template_id=template,additions=additions,fills=fills)
        after,_=await prepare_catalog_changes(db,template_id=template)
        numbers={r['catalog_direction_number']for r in after['direction_matches']}
        if numbers!={1,2,3,4,5,6} or after['template_direction_count']!=6:
            raise RuntimeError('Итоговое сопоставление шести направлений не подтверждено. Транзакция отменена.')
        backup['created']=[dict(table=obj.__tablename__,id=obj.id,values=snapshot(obj))for obj in objects]
        backup['phase']='ready_to_commit';write_backup(path,backup,replace=True)
        await db.commit()
        print('COMMITTED: six bilingual directions installed. Monthly tasks and assignments were not created.')
        print('Created rows:',len(objects))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--template-id',type=int)
    parser.add_argument('--academic-year',default='2026-2027')
    group=parser.add_mutually_exclusive_group();group.add_argument('--check',action='store_true');group.add_argument('--apply',action='store_true')
    parser.add_argument('--backup-dir',default=str(Path.home()/'Downloads'))
    parser.add_argument('--restore-backup')
    args=parser.parse_args()
    if not args.restore_backup and args.template_id is None:parser.error('--template-id is required')
    async def run():
        try:await main(args)
        finally:await engine.dispose()
    asyncio.run(run())
