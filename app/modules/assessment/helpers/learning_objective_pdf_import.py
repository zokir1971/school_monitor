# app/modules/assessment/helpers/learning_objective_pdf_import.py
"""Conservative table-cell extraction; all candidates require human approval."""
from __future__ import annotations
import io
import re
import pdfplumber

CODE = re.compile(r'(?<![\d.])((?:1[0-2]|[1-9])\s*\.\s*\d+\s*\.\s*\d+\s*\.\s*\d+)(?![\d.])')
SKILLS = (
    ('listening_speaking', ('тыңдалым және айтылым', 'слушание и говорение', 'аудирование и говорение')),
    ('listening', ('тыңдалым', 'слушание', 'аудирование')),
    ('speaking', ('айтылым', 'говорение')),
    ('reading', ('оқылым', 'чтение')),
    ('writing', ('жазылым', 'письмо')),
)


def clean(value):
    return re.sub(r'\s+', ' ', value or '').strip()


def pages_from_string(value, *, total):
    pages = set()
    for part in value.split(','):
        part = part.strip()
        if not re.fullmatch(r'\d+(?:\s*-\s*\d+)?', part):
            raise ValueError('Страницы: например 7-12,15. Используйте номера страниц PDF.')
        ends = [int(x.strip()) for x in part.split('-')]
        start, stop = ends[0], ends[-1]
        if not 1 <= start <= stop <= total:
            raise ValueError(f'Диапазон страниц должен быть в пределах 1–{total}.')
        if stop - start > 59:
            raise ValueError('За один импорт можно обработать до 60 страниц каждого PDF.')
        pages.update(range(start, stop + 1))
    if not pages or len(pages) > 60:
        raise ValueError('Выберите от 1 до 60 страниц каждого PDF.')
    return sorted(pages)


def extract_candidates(content, *, pages, grade_from, grade_to):
    if not content.startswith(b'%PDF-'):
        raise ValueError('Файл не является PDF.')
    warnings, result = [], []
    seen = {}
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        selected = pages_from_string(pages, total=len(pdf.pages))
        skill, section_title = None, ''
        for number in selected:
            page = pdf.pages[number - 1]
            tables = page.extract_tables()
            if not tables:
                warnings.append(f'Страница {number}: таблицы не распознаны; проверьте PDF и добавьте цели вручную.')
                continue
            for table in tables:
                for row in table:
                    # Only table headings, not arbitrary objective prose, identify a skill.
                    cells = [clean(cell) for cell in row]
                    if not any(CODE.search(cell) for cell in cells):
                        heading = ' '.join(cells).lower()
                        if any(('бөлім' in cell.lower() and 'бөлімше' not in cell.lower()) or (
                                'раздел' in cell.lower() and 'подраздел' not in cell.lower()) for cell in cells):
                            section_title = next((cell for cell in cells if
                                                  ('бөлім' in cell.lower() and 'бөлімше' not in cell.lower()) or (
                                                          'раздел' in cell.lower() and
                                                          'подраздел' not in cell.lower())),
                                                 '')
                            skill = next((key for key, labels in SKILLS if any(label in heading for label in labels)),
                                         None)
                        elif any(cells) and not any(word in heading for word in
                                                    ('сынып', 'класс', 'мақсат', 'цели', 'бөлімше', 'подраздел')):
                            warnings.append(
                                f'Страница {number}: строка без кода; возможное продолжение цели. Проверьте текст по '
                                f'PDF.')
                        continue
                    subsection = cells[0] if cells and not CODE.search(cells[0]) else ''
                    for cell in cells:
                        matches = list(CODE.finditer(cell))
                        for index, match in enumerate(matches):
                            code = re.sub(r'\s+', '', match.group(1))
                            grade = int(code.split('.')[0])
                            if not grade_from <= grade <= grade_to:
                                continue
                            title = cell[match.end():matches[index + 1].start() if index + 1 < len(matches) else len(
                                cell)].strip(' ;–-')
                            if not title:
                                warnings.append(f'Страница {number}: {code} без текста; требуется исправление.')
                            entry = {'code': code, 'grade_level': grade, 'title': title, 'pages': [number],
                                     'section_code': code.split('.')[1],
                                     'subsection_code': '.'.join(code.split('.')[1:3]),
                                     'section_title': section_title, 'subsection_title': subsection,
                                     'language_skill': skill}
                            identity = (code, title)
                            if identity in seen:
                                previous = seen[identity]
                                previous['pages'] = sorted(set(previous['pages'] + [number]))
                            else:
                                seen[identity] = entry;
                                result.append(entry)
                                if len(result) > 1000:
                                    raise ValueError(
                                        'Слишком много целей. Уменьшите диапазон страниц.')
    return result, list(dict.fromkeys(warnings))


def merge_languages(kz, ru):
    rows = []
    # Merge only unambiguous one-to-one code pairs. Alternatives remain visible.
    by_kz, by_ru = {}, {}
    for entry in kz:
        by_kz.setdefault(entry['code'], []).append(entry)
    for entry in ru:
        by_ru.setdefault(entry['code'], []).append(entry)
    for code in sorted(set(by_kz) | set(by_ru), key=lambda x: tuple(map(int, x.split('.')))):
        left, right = by_kz.get(code, []), by_ru.get(code, [])
        pairs = [(left[0], right[0])] if len(left) == len(right) == 1 else [(x, None) for x in left] + [(None, x) for x
                                                                                                        in right]
        for k, r in pairs:
            e = k or r
            rows.append({'code': code, 'grade_level': e['grade_level'], 'quarter': None,
                         'title_kz': k['title'] if k else '', 'title_ru': r['title'] if r else '',
                         'section_code': e['section_code'], 'subsection_code': e['subsection_code'],
                         'section_title_kz': k['section_title'] if k else '',
                         'section_title_ru': r['section_title'] if r else '',
                         'subsection_title_kz': k['subsection_title'] if k else '',
                         'subsection_title_ru': r['subsection_title'] if r else '',
                         'language_skill': e['language_skill'] or '', 'source_pages_kz': k['pages'] if k else [],
                         'source_pages_ru': r['pages'] if r else []})
    return rows
