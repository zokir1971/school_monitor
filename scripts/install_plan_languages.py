"""Check/apply the bundled bilingual content. Does not replace legacy columns."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,asyncio,gzip,json
from datetime import datetime
from sqlalchemy import select,update,func,and_
from app.db.session import async_session_maker,engine
from app.db.base import Base
from app.modules.planning.models import PlanTemplate
from app.modules.planning.models_school import SchoolPlan
from app.modules.planning.content_import import prepare_catalog_changes


async def template_choices(db, academic_year):
    """Small scalar projection: never load school/template relationships."""
    t, p = PlanTemplate.__table__, SchoolPlan.__table__
    stmt = select(t.c.id, t.c.name, t.c.academic_year, t.c.is_active,
        func.count(p.c.id).label('active_school_plans_for_year')).outerjoin(p, and_(
            p.c.template_id == t.c.id, p.c.academic_year == academic_year,
            p.c.status != 'archived')).group_by(
                t.c.id, t.c.name, t.c.academic_year, t.c.is_active).order_by(t.c.id)
    return [dict(row) for row in (await db.execute(stmt)).mappings()]


def choose_template(choices, academic_year, explicit_id=None):
    if explicit_id is not None:
        matches = [row for row in choices if row['id'] == explicit_id]
        reason = 'explicit_template_id'
    else:
        # The actual FK of the current school plans is authoritative. A shared
        # template may keep an old/empty year or have been deactivated later.
        matches = [row for row in choices if row['active_school_plans_for_year'] > 0]
        reason = 'school_plans_for_academic_year'
        if not matches:
            matches = [row for row in choices if row['academic_year'] == academic_year and row['is_active']]
            reason = 'active_template_for_academic_year'
    if len(matches) != 1:
        raise RuntimeError('Не удалось однозначно выбрать шаблон. Укажите --template-id с ID из выведенного списка. База не изменена.')
    return matches[0], reason


async def main(args):
    async with async_session_maker() as db:
        db.sync_session.info['planning_i18n_seed']=True
        if args.restore_backup:
            with gzip.open(args.restore_backup,'rt',encoding='utf-8')as f:backup=json.load(f)
            if backup.get('schema')!='planning-text-331':raise RuntimeError('Unknown backup format')
            # Check every row before restoring any; refuse to overwrite later edits.
            for change in backup['changes']:
                table=Base.metadata.tables[change['table']]
                current=(await db.execute(select(table.c.text_i18n).where(table.c.id==change['id']).with_for_update())).scalar_one_or_none()
                if current!=change['after']:raise RuntimeError(f"Row changed after installation: {change['table']} #{change['id']}")
            if not args.apply:
                print(f"RESTORE CHECK: {len(backup['changes'])} rows; database unchanged.");return
            for change in backup['changes']:
                table=Base.metadata.tables[change['table']]
                await db.execute(update(table).where(table.c.id==change['id']).values(text_i18n=change['before']))
            await db.commit();print('RESTORED language payloads; existing source fields and task history unchanged.');return
        choices = await template_choices(db, args.academic_year)
        if getattr(args, 'list_templates', False):
            print(json.dumps({'academic_year': args.academic_year, 'templates': choices}, ensure_ascii=False, indent=2))
            print('LIST ONLY: database unchanged.')
            return
        try:
            chosen, reason = choose_template(choices, args.academic_year, args.template_id)
        except RuntimeError:
            print(json.dumps({'academic_year': args.academic_year, 'templates': choices}, ensure_ascii=False, indent=2))
            raise
        selected_id = chosen['id']
        print(json.dumps({'selected_template': chosen, 'selection_reason': reason}, ensure_ascii=False, indent=2))
        # Lock the selected identity, without requiring its own year to equal the
        # year of the school plans that actually reference it.
        existing = await db.scalar(select(PlanTemplate.id).where(PlanTemplate.id == selected_id).with_for_update())
        if existing is None:
            raise RuntimeError('Шаблон удалён во время проверки. База не изменена; повторите команду.')
        report,changes=await prepare_catalog_changes(db,template_id=selected_id)
        report['selection_reason'] = reason
        report['school_plan_scope'] = 'all school plans linked to selected template; no source text or workflow changes'
        print(json.dumps(report,ensure_ascii=False,indent=2))
        if not args.apply:
            print('CHECK ONLY: database unchanged. Use --apply to install matched language fields.');return
        if report['directions_matched']!=6:
            raise RuntimeError('Not all six directions could be matched. No content installed; send the check report.')
        if not changes:print('ALREADY INSTALLED: no changes.');return
        folder=Path(args.backup_dir).expanduser();folder.mkdir(parents=True,exist_ok=True)
        backup=folder/('school_monitor_plan_languages331_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.json.gz')
        with backup.open('xb')as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb')as stream:
                stream.write(json.dumps({'schema':'planning-text-331','report':report,'changes':changes},ensure_ascii=False).encode('utf-8'))
        print('Backup:',backup)
        for change in changes:
            table=Base.metadata.tables[change['table']]
            # Optimistic guard: another editor cannot be overwritten between read and write.
            result=await db.execute(update(table).where(table.c.id==change['id'],table.c.text_i18n==change['before']).values(text_i18n=change['after']))
            if result.rowcount!=1:raise RuntimeError('Concurrent edit detected. Transaction rolled back; rerun check.')
        await db.commit();print('COMMITTED: language fields installed; source text, IDs, exclusions and task history preserved.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--academic-year',default='2026-2027')
    parser.add_argument('--template-id',type=int)
    parser.add_argument('--list-templates',action='store_true')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--backup-dir',default=str(Path.home()/'Downloads'))
    parser.add_argument('--restore-backup')
    args=parser.parse_args()
    if args.check and args.apply:parser.error('Choose --check or --apply')
    if args.list_templates and (args.apply or args.restore_backup):parser.error('--list-templates is read-only and cannot be combined with apply/restore')
    async def run():
        try:await main(args)
        finally:await engine.dispose()
    asyncio.run(run())
