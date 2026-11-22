"""Read-only checks for the existing batch staff importer."""
from sqlalchemy import select
from app.core.import_guard275 import MAX_BYTES, digest, summary
from app.modules.staff.models_staff_school import SchoolStaffMember as Member
from app.modules.staff.utils.csv_tools import read_csv_bytes, get_iin, build_full_name, map_row_to_fields, get_value
from app.modules.staff.utils.staff_position_filter import is_allowed_staff


def parse(raw):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Файл пуст или превышает 15 МБ.')
    data = read_csv_bytes(raw)
    if len(data.rows) > 20000:
        raise ValueError('В файле более 20 000 строк.')
    rows, seen, organizations = [], set(), set()
    skipped = 0
    for record in data.rows:
        if None in record:
            raise ValueError('В строке лишние колонки. Проверьте разделитель CSV-файла.')
        organization = get_value(record, 'Наименование организации [external_name_organization]',
                                 'Наименование организации', 'Ұйымның атауы')
        if organization:
            organizations.add(organization)
        iin = get_iin(record)
        name = build_full_name(record)
        fields = map_row_to_fields(record)
        if not iin or not name or not is_allowed_staff(position_text=fields.get('position_text')):
            skipped += 1
            continue
        if iin in seen:
            raise ValueError('Повтор ИИН в файле. Устраните дубли и загрузите файл снова.')
        if len(name) > 200:
            raise ValueError('ФИО превышает 200 символов. Исправьте файл.')
        seen.add(iin)
        rows.append(dict(iin=iin, full_name=name, position=fields.get('position_text')))
    if len(organizations) > 1:
        raise ValueError('В файле несколько организаций. Подготовьте выгрузку одной школы.')
    if not rows:
        raise ValueError('Нет сотрудников для импорта. Проверьте формат файла и должности.')
    return dict(rows=rows, skipped=skipped, organizations=sorted(organizations))


async def snapshot(db, school_id, data):
    table = Member.__table__
    fields = ['id', 'iin', 'full_name', 'is_active', 'position_text', 'education',
              'academic_degree', 'qualification_category']
    state = (await db.execute(select(*(table.c[key] for key in fields))
                             .where(table.c.school_id == school_id).order_by(table.c.id))).all()
    existing = {row.iin for row in state}
    new = sum(row['iin'] not in existing for row in data['rows'])
    return summary(len(data['rows']), new, len(state)), digest([list(row) for row in state])
