"""Pure parser: no database writes and no personal data in diagnostics."""
from __future__ import annotations
import csv
import io
import re
from datetime import datetime

MAX_BYTES = 15 * 1024 * 1024


def clean(value):
    value = (value or '').strip()
    if value.startswith('="') and value.endswith('"'):
        value = value[2:-1]
    return value.strip()


def parse_nobd(raw: bytes):
    if not raw or len(raw) > MAX_BYTES:
        raise ValueError('Файл пуст или превышает 15 МБ.')
    try:
        text = raw.decode('utf-16' if raw.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('Ожидается выгрузка НОБД в UTF-16 или UTF-8.') from exc
    reader = csv.DictReader(io.StringIO(text), delimiter='\t')
    required = ['ИИН', 'Фамилия', 'Имя', 'Параллель [207]', 'Литера [6668]']
    if not reader.fieldnames or any(k not in reader.fieldnames for k in required):
        raise ValueError('Не найдены обязательные колонки выгрузки НОБД (разделитель — табуляция).')
    rows, errors, groups, seen = [], [], {}, set()
    skipped = 0
    organizations = set()
    for line, record in enumerate(reader, 2):
        if line > 20002:
            raise ValueError('В файле более 20 000 строк.')
        if not any(record.values()):
            continue
        r = {k: clean(v) for k, v in record.items() if k is not None}
        try:
            if None in record:
                raise ValueError('лишние колонки')
            grade_text = r['Параллель [207]']
            match = re.fullmatch(r'(\d{1,2})(?:\s*(?:класс|сынып))?', grade_text, re.IGNORECASE)
            if not match:
                raise ValueError('некорректная параллель')
            grade = int(match.group(1))
            if grade == 0:
                skipped += 1
                continue
            if not 1 <= grade <= 12:
                raise ValueError('параллель должна быть от 1 до 12')
            iin = r['ИИН']
            if not re.fullmatch(r'[0-9]{12}', iin):
                raise ValueError('ИИН должен содержать 12 цифр')
            if iin in seen:
                raise ValueError('повтор ИИН в файле')
            seen.add(iin)
            letter = r['Литера [6668]'].upper()
            if not letter or len(letter) > 20:
                raise ValueError('некорректная литера')
            for key in ['Фамилия', 'Имя']:
                if not r[key] or len(r[key]) > 150:
                    raise ValueError('не заполнены или слишком длинные ФИО')
            middle = r.get('Отчество', '')
            if len(middle) > 150:
                raise ValueError('слишком длинное отчество')
            birth = r.get('Дата рождения', '')
            if birth:
                try:
                    birth = datetime.strptime(birth, '%d.%m.%Y').date().isoformat()
                except ValueError:
                    try:
                        birth = datetime.strptime(birth, '%Y-%m-%d').date().isoformat()
                    except ValueError as exc:
                        raise ValueError('некорректная дата рождения') from exc
            key = f'{grade}:{letter}'
            group = groups.setdefault(key,
                                      {'key': key, 'grade': grade, 'letter': letter, 'count': 0, 'languages': set()})
            group['count'] += 1
            group['languages'].add(r.get('Язык обучения [209]', '') or 'Не указан')
            org = r.get('Наименование организации [external_name_organization]', '')
            if org:
                organizations.add(org)
            rows.append(dict(iin=iin, last_name=r['Фамилия'], first_name=r['Имя'], middle_name=middle or None,
                             birth_date=birth or None, key=key))
        except ValueError as exc:
            errors.append(f'Строка {line}: {exc}.')
    if not rows and not errors:
        errors.append('Нет учеников 1–12 классов для импорта.')
    if len(organizations) > 1:
        errors.append('Файл содержит несколько организаций. Подготовьте выгрузку одной школы.')
    return {'rows': rows, 'groups': [dict(g, languages=sorted(g['languages'])) for g in
                                     sorted(groups.values(), key=lambda g: (g['grade'], g['letter']))],
            'errors': errors, 'skipped': skipped, 'organizations': sorted(organizations)}
