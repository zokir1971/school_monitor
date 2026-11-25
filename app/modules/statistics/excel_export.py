"""Filtered, role-scoped exports. All rows, no per-school queries."""
from io import BytesIO
from datetime import datetime
from types import SimpleNamespace
from sqlalchemy import select, text, func
from app.modules.statistics.territorial_service import TerritorialStatisticsService
from app.modules.statistics.territorial_repo import TerritorialStatisticsRepo, ordered_groups
from app.modules.statistics.activity_service import ActivityStatisticsService, school_facts, grouped, MODULE_LABELS
from app.modules.statistics.activity_tracking import LOCAL_TZ
from app.core.planning_profile import measure_export_phase

TITLES = {'regions': ('Регионы', 'Өңірлер'), 'districts': ('Районы', 'Аудандар'),
          'schools': ('Школы', 'Мектептер'), 'directions': ('Направления ВШК', 'МІБ бағыттары')}


def percent(row, numerator, denominator):
    return row[numerator] / row[denominator] if row[denominator] else None


def stamp(value):
    if value is None:
        return ''
    from datetime import timezone
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime('%d.%m.%Y %H:%M')


async def collect(db, user, params, *, activity=False):
    # Authentication already completed; preserve scalar identity before rollback.
    actor = SimpleNamespace(**{key: getattr(user, key, None) for key in
                              ('id', 'role', 'is_active', 'region_id', 'district_id', 'school_id')})
    snapshot = db.bind.dialect.name == 'postgresql'
    if snapshot:
        await db.rollback()
        await db.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
        await db.execute(text('SET TRANSACTION READ ONLY'))
    try:
        if activity:
            data = await ActivityStatisticsService.page(db, actor, params)
            facts = school_facts(data['start'], data['end'], data['region_id'], data['district_id'], data['q'], data['governance'])
            if data['attention']:
                from sqlalchemy import or_
                facts = select(facts).where(or_(facts.c.ready == 0, facts.c.worked == 0)).cte('export_attention_facts')
            views = ('regions', 'districts', 'schools')
            sheets = []
            for view in views:
                groups = grouped(facts, view, data['region_id'], data['district_id'],data['governance'])
                metric = {'name': groups.c.name, 'worked': groups.c.worked,
                          'rate': 100.0 * groups.c.worked / func.nullif(groups.c.schools, 0),
                          'last_work': groups.c.last_work}[data['sort']]
                primary = (metric.asc() if data['order'] == 'asc' else metric.desc()).nullslast()
                query = select(groups).order_by(primary, groups.c.name, groups.c.id)
                if view == 'regions' and data['region_id']:
                    query = query.where(groups.c.id == data['region_id'])
                rows = [dict(row) for row in (await db.execute(query)).mappings()]
                for row in rows:
                    row['inactive'] = row['schools'] - row['worked']
                sheets.append((view, rows))
            # Bounded extra metadata read to disambiguate equally named schools.
            from app.modules.org.models import School, District, Region
            s, d, r = School.__table__.c, District.__table__.c, Region.__table__.c
            query = select(s.id, d.name.label('district_name'), r.name.label('region_name')).select_from(
                School.__table__.join(District.__table__, s.district_id == d.id).join(Region.__table__, d.region_id == r.id)).join(facts, facts.c.school_id == s.id)
            names = {row['id']: row for row in (await db.execute(query)).mappings()}
            for view, rows in sheets:
                if view == 'schools':
                    for row in rows:
                        row.update({key: names[row['id']][key] for key in ('region_name', 'district_name')})
                elif view == 'districts':
                    for row in rows:
                        rid=-row['id'] if row['id']<0 else next(item['region_id'] for item in data['districts'] if item['id']==row['id'])
                        row['region_name'] = next(item['name'] for item in data['regions'] if item['id']==rid)
        else:
            data = await TerritorialStatisticsService.page(db, actor, params)
            scope = data['scope']
            schools = TerritorialStatisticsRepo.school_scope(scope, data['district_id'], data['school_id'], data['q'], data['governance'])
            views = ('regions', 'districts', 'schools', 'directions') if scope['kind'] == 'super' else (
                ('districts', 'schools', 'directions') if scope['kind'] == 'region' else ('schools', 'directions'))
            sheets = []
            for view in views:
                _, groups = TerritorialStatisticsRepo.query(schools, data['year'], data['month'], data['direction_id'], view,
                                                             data['today'], attention=bool(data['attention'] and not data['school_id']))
                query = ordered_groups(groups, view, data['sort'], data['order'])
                if view == 'regions' and data['region_id']:
                    query = query.where(groups.c.id == data['region_id'])
                rows = [dict(row) for row in (await db.execute(query)).mappings()]
                sheets.append((view, rows))
        return data, sheets
    finally:
        if snapshot:
            await db.rollback()  # Release snapshot before ZIP/XML generation.


def workbook(data, sheets, language, *, activity=False):
    """Run in the thread pool. Strings are literal, never Excel formulas."""
    with measure_export_phase('excel_import'):
        from openpyxl import Workbook
        from openpyxl.cell import WriteOnlyCell
        from openpyxl.styles.borders import DEFAULT_BORDER
        from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle
        from openpyxl.utils import get_column_letter
        from openpyxl.worksheet.worksheet import Worksheet
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    ru = language == 'ru'
    choose = lambda rz, kz: rz if ru else kz
    with measure_export_phase('excel_styles'):
        wb = Workbook(write_only=True)
        alignment = Alignment(vertical='top', wrap_text=True)
        body = Font(name='Calibri', size=11)
        bold = Font(name='Calibri', size=11, bold=True, color='17365D')
        header_fill = PatternFill('solid', fgColor='E8F0FC')
        # Bind each named style once per workbook, then reuse the registered
        # style instead of constructing and hashing font/alignment per cell.
        for name, heading, percentage in (
            ('stats_body', False, False), ('stats_heading', True, False),
            ('stats_percent', False, True), ('stats_total_percent', True, True),
        ):
            style = NamedStyle(name=name, font=bold if heading else body, alignment=alignment, border=DEFAULT_BORDER,
                               number_format='0.0%' if percentage else 'General')
            if heading:
                style.fill = header_fill
            wb.add_named_style(style)
    for view, rows in sheets:
        ws = wb.create_sheet(TITLES[view][0 if ru else 1])
        columns = [('id', 'ID', 'ID'), ('name', *TITLES[view])]
        if view in ('schools', 'districts'):
            columns.append(('region_name', 'Регион', 'Өңір'))
        if view == 'schools':
            columns.append(('district_name', 'Район / город', 'Аудан / қала'))
        if activity:
            columns += [('schools', 'Школы', 'Мектептер'), ('ready', 'Доступ настроен', 'Қолжетімділік бапталған'),
                        ('entered', 'Входили', 'Жүйеге кірген'), ('worked', 'Работали', 'Жұмыс істеген'),
                        ('inactive', 'Без рабочих событий', 'Жұмыс оқиғалары жоқ'),
                        ('activity_rate', 'Доля активности', 'Белсенділік үлесі'),
                        ('last_work', 'Последняя работа в периоде (UTC+5)', 'Кезеңдегі соңғы жұмыс (UTC+5)')]
            if view == 'schools':
                columns += [('last_login', 'Последний вход (UTC+5)', 'Соңғы кіру (UTC+5)'),
                            ('modules', 'Модули', 'Модульдер'), ('reasons', 'Причины внимания', 'Назар аудару себептері')]
        else:
            columns += [('schools', 'Школы / охват', 'Мектептер / қамту'), ('annual', 'Годовой план', 'Жылдық жоспар'),
                        ('monthly', 'Выпущенный месячный план', 'Шығарылған айлық жоспар'),
                        ('direction_schools', 'Школы с задачами', 'Тапсырмасы бар мектептер'),
                        ('tasks', 'Задачи', 'Тапсырмалар'), ('assigned', 'Назначены', 'Тағайындалды'),
                        ('unassigned', 'Не назначены', 'Тағайындалмаған'), ('assigned_rate', 'Доля назначений', 'Тағайындау үлесі'),
                        ('completed', 'Завершено', 'Аяқталған'), ('completion_rate', 'Доля завершения', 'Аяқталу үлесі'),
                        ('in_progress', 'В работе', 'Орындалуда'), ('todo', 'Запланированы', 'Жоспарланған'),
                        ('not_executed', 'Не выполнены', 'Орындалмаған'), ('overdue', 'Просрочено', 'Кешіккен'),
                        ('overdue_rate', 'Доля просрочек', 'Кешігу үлесі'), ('reports', 'Системные отчёты', 'Жүйелік есептер'),
                        ('submitted', 'Сданы', 'Тапсырылды'), ('submitted_rate', 'Доля сданных отчётов', 'Тапсырылған есептер үлесі'),
                        ('drafts', 'Доработка', 'Толықтыру'), ('waiting', 'Ожидаются', 'Күтілуде'),
                        ('reviewed', 'Рассмотрены', 'Қаралған'), ('review_waiting', 'Ожидают рассмотрения', 'Қарауды күтуде')]
            if view == 'schools':
                columns.append(('reasons', 'Причины внимания', 'Назар аудару себептері'))
        ws.row_dimensions[6].height = 90
        ws.row_dimensions[8].height = 46
        ws.freeze_panes = 'C9'
        ws.sheet_view.zoomScale = 85
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.orientation = 'landscape'
        ws.page_setup.paperSize = Worksheet.PAPERSIZE_A3
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.print_title_rows = '1:8'
        for i, (key, _, _) in enumerate(columns, 1):
            ws.column_dimensions[get_column_letter(i)].width = 52 if key in ('name', 'reasons') else 32 if key in ('region_name', 'district_name', 'modules') else 22

        def append(values, heading=False):
            cells = []
            for value in values:
                if isinstance(value, str): value = ILLEGAL_CHARACTERS_RE.sub('', value)
                cell = WriteOnlyCell(ws, value=value)
                if isinstance(value, str):
                    cell.data_type = 's'
                cell.style = 'stats_heading' if heading else 'stats_body'
                cells.append(cell)
            ws.append(cells)
            return cells

        title = choose('Активность школ', 'Мектептердің белсенділігі') if activity else choose('Статистика ВШК', 'МІБ статистикасы')
        append([title, TITLES[view][0 if ru else 1]], True)
        append([choose('Период', 'Кезең'), f"{data['start']} — {data['end']}" if activity else f"{data['year']}–{data['year']+1}; " + str(data['month'] or choose('Весь учебный год', 'Толық оқу жылы'))])
        regions = data.get('regions', [])
        region_name = next((item['name'] for item in regions if item['id'] == data.get('region_id')), data.get('scope', {}).get('name', ''))
        district_name = next((item['name'] for item in data['districts'] if item['id'] == data.get('district_id')), '')
        append([choose('Территория', 'Аумақ'), region_name or choose('Все доступные территории', 'Барлық қолжетімді аумақтар'), district_name, data.get('school_name', '')])
        direction_name = next((item['name'] for item in data.get('directions', []) if item['id'] == data.get('direction_id')), choose('Без направления', 'Бағыт көрсетілмеген') if data.get('direction_id') == 0 else choose('Все направления', 'Барлық бағыттар'))
        append([choose('Фильтры', 'Сүзгілер'), '' if activity else direction_name, choose('Поиск: ', 'Іздеу: ') + data['q'], choose('Требуют внимания', 'Назар аударуды қажет етеді') if data['attention'] else choose('Все школы', 'Барлық мектептер'), choose('Подчинение: ', 'Бағыныстылық: ') + {'region':choose('Областное','Облыстық'),'district':choose('Районное','Аудандық')}.get(data.get('governance'),choose('Все','Барлығы'))])
        sort_labels = {'name': ('Название / порядок направлений', 'Атауы / бағыттар реті'), 'completed': ('Количество завершённых', 'Аяқталған саны'), 'overdue': ('Количество просрочек', 'Кешігу саны'), 'rate': ('Доля активности' if activity else 'Доля завершения', 'Белсенділік үлесі' if activity else 'Аяқталу үлесі'), 'overdue_rate': ('Доля просрочек', 'Кешігу үлесі'), 'assigned_rate': ('Доля назначений', 'Тағайындау үлесі'), 'submitted_rate': ('Доля сданных отчётов', 'Тапсырылған есептер үлесі'), 'worked': ('Работали', 'Жұмыс істеген'), 'last_work': ('Последняя работа', 'Соңғы жұмыс')}
        append([choose('Сортировка', 'Сұрыптау'), choose(*sort_labels[data['sort']]), choose('По возрастанию', 'Өсу ретімен') if data['order'] == 'asc' else choose('По убыванию', 'Кему ретімен'), choose('Сформировано (UTC+5)', 'Құрылды (UTC+5)'), stamp(datetime.now(LOCAL_TZ))])
        note = (choose('История начата: ', 'Тарих басталды: ') + stamp(data['started_at']) + ('; ' + choose('Период неполный', 'Кезең толық емес') if data['incomplete'] else '')) if activity else choose('Школы по направлениям не суммируются; пустой процент — нет знаменателя. Отчёты считаются по текущим версиям, как на странице.', 'Бағыттардағы мектеп саны қосылмайды; бос пайыз — бөлім жоқ. Есептер беттегідей ағымдағы нұсқалар бойынша саналады.')
        append([choose('Примечание', 'Ескертпе'), note])
        append([])
        append([choose(rz, kz) for _, rz, kz in columns], True)
        rates = {'activity_rate': ('worked', 'schools'), 'assigned_rate': ('assigned', 'tasks'),
                 'completion_rate': ('completed', 'tasks'), 'overdue_rate': ('overdue', 'tasks'),
                 'submitted_rate': ('submitted', 'reports')}

        def values_for(row):
            values = []
            for key, _, _ in columns:
                if key in rates:
                    value = percent(row, *rates[key])
                elif key in ('last_login', 'last_work'):
                    value = stamp(row.get(key))
                elif key == 'unassigned':
                    value = row['tasks'] - row['assigned']
                elif key == 'modules':
                    value = ', '.join(labels[0 if ru else 1] for code, labels in MODULE_LABELS.items() if row.get(code))
                elif key == 'reasons':
                    reasons = []
                    if not row.get('ready' if activity else 'has_admin'):
                        reasons.append(choose('Нет активного администратора', 'Белсенді әкімші жоқ'))
                    if activity:
                        if not row.get('worked'): reasons.append(choose('Нет рабочих событий за период', 'Кезеңде жұмыс оқиғалары жоқ'))
                    else:
                        for condition, rz, kz in [(not row['annual'], 'Нет годового плана / направления', 'Жылдық жоспар / бағыт жоқ'),
                                                  (not row['monthly'], 'Нет выпущенного месячного плана / задач направления', 'Шығарылған айлық жоспар / бағыт тапсырмасы жоқ'),
                                                  (row['assigned'] < row['tasks'], 'Есть неназначенные задачи', 'Тағайындалмаған тапсырмалар бар'),
                                                  (row['overdue'] > 0, 'Есть просроченные задачи', 'Мерзімі өткен тапсырмалар бар')]:
                            if condition: reasons.append(choose(rz, kz))
                    value = '; '.join(reasons)
                else:
                    value = row.get(key, '')
                values.append(value)
            return values

        # Percentage cells remain numeric and sortable in Excel.
        row_number = 8
        def append_record(row, total=False):
            nonlocal row_number
            row_number += 1
            with measure_export_phase('excel_rows'):
                values = values_for(row)
                line_count = 1
                for i, ((key, _, _), value) in enumerate(zip(columns, values)):
                    if total and key in ('reasons','modules','last_login','last_work','region_name','district_name'):
                        value = ''
                    if isinstance(value, str):
                        value = ILLEGAL_CHARACTERS_RE.sub('', value)
                        width = 50 if key in ('name','reasons') else 30 if key in ('region_name','district_name','modules') else 20
                        line_count = max(line_count, (len(value) + width - 1) // width)
                    values[i] = value
            with measure_export_phase('excel_cells'):
                cells = []
                for (key, _, _), value in zip(columns, values):
                    cell = WriteOnlyCell(ws, value=value)
                    if isinstance(value, str):
                        cell.data_type = 's'
                    cell.style = ('stats_total_percent' if total else 'stats_percent') if key in rates else ('stats_heading' if total else 'stats_body')
                    cells.append(cell)
                ws.row_dimensions[row_number].height = min(120, max(28, line_count * 15))
                ws.append(cells)

        for row in rows:
            if view == 'directions' and not row['name']:
                row = dict(row, name=choose('Без направления', 'Бағыт көрсетілмеген'))
            append_record(row)
        ws.auto_filter.ref = f'A8:{get_column_letter(len(columns))}{8+len(rows)}'
        totals = dict(data['totals'], id='', name=choose('Итого по выборке', 'Іріктеу бойынша барлығы'))
        append_record(totals, total=True)
    buffer = BytesIO()
    with measure_export_phase('excel_finalize'):
        wb.save(buffer)
    return buffer.getvalue()
