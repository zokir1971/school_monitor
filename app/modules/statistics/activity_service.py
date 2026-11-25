"""Superuser school adoption statistics: SQL aggregates and bounded pages."""
from datetime import date, datetime, time, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select, func, case, literal, and_, or_
from app.modules.org.models import School, District, Region
from app.modules.org.governance import governance_filter, reporting_district_id, reporting_district_name
from app.modules.users.models import User
from app.modules.statistics.activity_tables import activity_days, activity_state
from app.modules.statistics.activity_tracking import LOCAL_TZ
from app.modules.statistics.territorial_service import integer

MODULE_LABELS = {
    'planning': ('Планирование', 'Жоспарлау'), 'tasks': ('Задачи', 'Тапсырмалар'),
    'reports': ('Отчёты', 'Есептер'), 'reviews': ('Рассмотрение', 'Қарау'),
    'staff': ('Персонал', 'Қызметкерлер'), 'education': ('Образование', 'Білім беру'),
    'assessment': ('Оценивание', 'Бағалау'),
}
METRICS = ('schools', 'ready', 'entered', 'worked')


def period(params, today):
    preset = params.get('period') or '30'
    if preset not in ('1', '7', '30', 'custom'):
        raise HTTPException(400, 'Некорректный период / Кезең қате')
    if preset == 'custom':
        try:
            start, end = date.fromisoformat(params.get('start', '')), date.fromisoformat(params.get('end', ''))
        except (ValueError, TypeError):
            raise HTTPException(400, 'Укажите даты / Күндерді көрсетіңіз')
    else:
        start, end = today - timedelta(days=int(preset) - 1), today
    if start > end or end > today or start < date(2000, 1, 1) or (end - start).days > 365:
        raise HTTPException(400, 'Период: до 366 дней, без будущих дат / Кезең: 366 күнге дейін')
    return preset, start, end


def school_facts(start, end, region_id=None, district_id=None, search='', governance=''):
    s, d, u, a = School.__table__.c, District.__table__.c, User.__table__.c, activity_days.c
    accounts = select(u.school_id, literal(1).label('ready')).where(
        u.role == 'school_admin', u.is_active.is_(True), u.school_id.is_not(None),
    ).group_by(u.school_id).cte('active_school_admins')
    activity = select(
        a.school_id,
        func.max(case((a.module == 'login', 1), else_=0)).label('entered'),
        func.max(case((a.module != 'login', 1), else_=0)).label('worked'),
        func.max(case((a.module == 'login', a.last_at), else_=None)).label('last_login'),
        func.max(case((a.module != 'login', a.last_at), else_=None)).label('last_work'),
        *[func.max(case((a.module == key, 1), else_=0)).label(key) for key in MODULE_LABELS],
    ).where(a.day >= start, a.day <= end).group_by(a.school_id).cte('period_activity')
    stmt = select(
        s.id.label('school_id'), s.name.label('school_name'), reporting_district_id(d.id,d.region_id,level=s.governance_level).label('district_id'), d.region_id,
        reporting_district_name(d.name,s.governance_level).label('district_name'),
        literal(1).label('schools'), func.coalesce(accounts.c.ready, 0).label('ready'),
        func.coalesce(activity.c.entered, 0).label('entered'), func.coalesce(activity.c.worked, 0).label('worked'),
        activity.c.last_login, activity.c.last_work,
        *[func.coalesce(activity.c[key], 0).label(key) for key in MODULE_LABELS],
    ).select_from(School.__table__.join(District.__table__, s.district_id == d.id)
                  .outerjoin(accounts, accounts.c.school_id == s.id)
                  .outerjoin(activity, activity.c.school_id == s.id))
    if region_id:
        stmt = stmt.where(d.region_id == region_id)
    if district_id:
        stmt = stmt.where(d.id == district_id, s.governance_level == 'district')
    if governance:
        stmt = stmt.where(s.governance_level == governance)
    if search:
        term = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        stmt = stmt.where(s.name.ilike('%' + term + '%', escape='\\'))
    return stmt.cte('school_activity_facts')


def grouped(facts, view, region_id, district_id, governance=''):
    if view == 'schools':
        return select(facts.c.school_id.label('id'), facts.c.school_name.label('name'), *[
            facts.c[key] for key in (*METRICS, 'last_login', 'last_work', *MODULE_LABELS)
        ]).cte('activity_groups')
    table = Region.__table__ if view == 'regions' else District.__table__
    key = facts.c.region_id if view == 'regions' else facts.c.district_id
    stmt = select(table.c.id, table.c.name, func.max(facts.c.last_work).label('last_work'), *[
        func.coalesce(func.sum(facts.c[key]), 0).label(key) for key in METRICS
    ]).select_from(table.outerjoin(facts, key == table.c.id))
    if view == 'districts' and region_id:
        stmt = stmt.where(table.c.region_id == region_id)
    if view == 'districts' and district_id:
        stmt = stmt.where(table.c.id == district_id)
    if view=='districts' and governance=='region':stmt=stmt.where(literal(False))
    stmt=stmt.group_by(table.c.id, table.c.name)
    if view=='districts':
        from sqlalchemy import union_all
        direct=select(facts.c.district_id.label('id'),func.max(facts.c.district_name).label('name'),func.max(facts.c.last_work).label('last_work'),*[func.sum(facts.c[key]).label(key) for key in METRICS]).where(facts.c.district_id<0).group_by(facts.c.district_id)
        stmt=union_all(stmt,direct)
    return stmt.cte('activity_groups')


class ActivityStatisticsService:
    @staticmethod
    async def page(db, user, params, today=None):
        if not user.is_active or getattr(user.role, 'value', user.role) != 'superuser':
            raise HTTPException(403, 'Нет доступа / Қолжетімділік жоқ')
        today = today or datetime.now(LOCAL_TZ).date()
        preset, start, end = period(params, today)
        region_id, district_id = integer(params.get('region_id')), integer(params.get('district_id'))
        page = integer(params.get('page'), 1)
        view = params.get('view') or ('schools' if district_id else 'districts' if region_id else 'regions')
        sort = params.get('sort') or 'name'
        if view not in ('regions', 'districts', 'schools') or sort not in ('name', 'worked', 'rate', 'last_work'):
            raise HTTPException(400, 'Некорректный вид или сортировка / Көрініс не сұрыптау қате')
        order = params.get('order') or ('asc' if sort == 'name' else 'desc')
        if order not in ('asc', 'desc'):
            raise HTTPException(400, 'Некорректный порядок / Реті қате')
        attention = integer(params.get('attention'), 0, 0, 1)
        if attention:
            view = 'schools'
        if view == 'regions' and (region_id or district_id):
            raise HTTPException(400, 'Сбросьте территорию для списка регионов / Аумақ сүзгісін тазалаңыз')
        q = (params.get('q') or '').strip()
        if len(q) > 150:
            raise HTTPException(400, 'Слишком длинный поиск / Іздеу мәтіні тым ұзын')
        # No readiness query on each page: the marker is also the start date.
        from sqlalchemy.exc import ProgrammingError
        try:
            started_at = await db.scalar(select(activity_state.c.started_at).where(activity_state.c.id == 1))
        except ProgrammingError as exc:
            if getattr(exc.orig, 'sqlstate', None) != '42P01':
                raise
            await db.rollback()
            raise HTTPException(503, 'Установите таблицы активности: setup_activity.py --project . --apply / Белсенділік кестелерін орнатыңыз') from None
        if started_at is None:
            raise HTTPException(503, 'Сбор активности не настроен / Белсенділік жинау бапталмаған')
        regions = [dict(row) for row in (await db.execute(select(Region.__table__.c.id, Region.__table__.c.name).order_by(Region.__table__.c.name))).mappings()]
        if region_id and region_id not in {r['id'] for r in regions}:
            raise HTTPException(400, 'Регион не найден / Өңір табылмады')
        d = District.__table__.c
        stmt = select(d.id, d.name, d.region_id)
        if region_id:
            stmt = stmt.where(d.region_id == region_id)
        districts = [dict(row) for row in (await db.execute(stmt.order_by(d.name, d.id))).mappings()]
        if district_id:
            chosen = next((row for row in districts if row['id'] == district_id), None)
            if chosen is None:
                raise HTTPException(400, 'Район не принадлежит региону / Аудан өңірге жатпайды')
            region_id = chosen['region_id']
            districts = [row for row in districts if row['region_id'] == region_id]
        try:governance=governance_filter(params.get('governance'))
        except ValueError as exc:raise HTTPException(400,str(exc)) from exc
        if governance=='region' and district_id is not None:raise HTTPException(400,'Для областных школ очистите выбор района / Облыстық мектептер үшін аудан таңдауын тазалаңыз')
        facts = school_facts(start, end, region_id, district_id, q,governance)
        if attention:
            facts = select(facts).where(or_(facts.c.ready == 0, facts.c.worked == 0)).cte('attention_activity_facts')
        groups = grouped(facts, view, region_id, district_id,governance)
        totals = dict((await db.execute(select(*[
            func.coalesce(func.sum(facts.c[key]), 0).label(key) for key in METRICS
        ], select(func.count()).select_from(groups).scalar_subquery().label('groups')))).mappings().one())
        pages = max(1, (totals['groups'] + 49) // 50)
        page = min(page, pages)
        metric = {'name': groups.c.name, 'worked': groups.c.worked,
                  'rate': 100.0 * groups.c.worked / func.nullif(groups.c.schools, 0),
                  'last_work': groups.c.last_work}[sort]
        primary = (metric.asc() if order == 'asc' else metric.desc()).nullslast()
        rows = [dict(row) for row in (await db.execute(select(groups).order_by(primary, groups.c.name, groups.c.id).limit(50).offset((page - 1) * 50))).mappings()]
        for row in (totals, *rows):
            row['inactive'] = row['schools'] - row['worked']
            row['percent'] = round(100 * row['worked'] / row['schools'], 1) if row['schools'] else None
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=timezone.utc)
        # The installation day is also partial; do not label it complete.
        incomplete = datetime.combine(start, time.min, LOCAL_TZ) < started_at
        return dict(governance=governance,period=preset, start=start, end=end, region_id=region_id, district_id=district_id,
                    regions=regions, districts=districts, view=view, sort=sort, order=order, attention=attention, q=q, totals=totals,
                    rows=rows, page=page, pages=pages, started_at=started_at.astimezone(LOCAL_TZ),
                    incomplete=incomplete, module_labels=MODULE_LABELS)
