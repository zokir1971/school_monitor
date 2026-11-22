"""Class matching and frozen per-class scores; never query current report data here."""
import re
import unicodedata

# Only visually equivalent letters; do not transliterate distinct school letters.
_LOOKALIKE = str.maketrans('abcehkmoptxy', 'авсенкмортху')


def class_key(name):
    text = unicodedata.normalize('NFKC', str(name or '')).strip().casefold()
    match = re.fullmatch(r'(1[0-2]|[1-9])[\s\-–—]*([^\W\d_])', text)
    if not match:
        return ('name', re.sub(r'\s+', '', text)) if text else None
    return int(match[1]), match[2].translate(_LOOKALIKE)


def class_index(classes):
    index = {}
    for cid, row in classes.items():
        key = class_key(row['name'])
        if key is not None:
            index.setdefault(key, set()).add(cid)
    return index


def matched_names(name, index):
    names = re.split(r'[,;]', str(name or ''))
    found = []
    for part in names:
        candidates = index.get(class_key(part), set())
        # Ambiguous names must not silently attach a score to the wrong class.
        if len(candidates) != 1:
            return None
        found.append(next(iter(candidates)))
    return found if found and len(found) == len(set(found)) else None


def source_rows(source, section, allowed, index):
    """Keep legacy whole-report totals; expand version-1 notebook class snapshots."""
    checks = source.get('notebook_checks')
    if section == 'notebooks' and source.get('notebook_checks_version') == 1:
        if not isinstance(checks, list) or not checks or len(checks) > 100:
            raise ValueError('Некорректный снимок классов исходного отчёта. / Бастапқы есептің сыныптар деректері дұрыс емес.')
        rows = []
        seen = set()
        for check in checks:
            if not isinstance(check, dict):
                raise ValueError('Некорректный снимок классов исходного отчёта. / Бастапқы есептің сыныптар деректері дұрыс емес.')
            cid, sid = check.get('class_id'), check.get('subject_id')
            identity = (cid, sid)
            if identity in seen:
                raise ValueError('Повтор класса в исходном отчёте. / Бастапқы есепте сынып қайталанған.')
            seen.add(identity)
            valid_id = type(cid) is int and cid in allowed
            in_scope = valid_id and (sid is None or sid in allowed[cid].get('subject_ids', ()))
            rows.append(dict(class_name=check.get('class_name') or '', class_id=cid,
                subject_id=sid, grade_level=check.get('grade_level') or (allowed[cid].get('grade_level') if valid_id else None), in_scope=in_scope,
                score=check.get('total_score'), max_score=check.get('max_score'),
                note=check.get('note') or source.get('notebook_conclusion') or ''))
        return rows
    name = source.get('lesson_class') if section == 'lessons' else source.get('notebook_class')
    matches = matched_names(name, index)
    return [dict(class_name=name, class_id=matches[0] if matches and len(matches) == 1 else None,
        subject_id=None, in_scope=bool(matches) and all(cid in allowed for cid in matches),
        score=source.get('lesson_score') if section == 'lessons' else source.get('notebook_score'),
        max_score=source.get('lesson_max') if section == 'lessons' else source.get('notebook_max'),
        note=(source.get('lesson_feedback') if section == 'lessons' else source.get('notebook_conclusion')) or '')]


def group_source_rows(sources):
    """Presentation rows only: keep original class evidence and scales intact."""
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

    output, groups = [], {}
    for source in sources:
        row = dict(source)
        key = class_key(row.get('class_name'))
        grade = row.get('grade_level')
        if type(grade) is not int or grade not in range(1, 13):
            grade = key[0] if key is not None and type(key[0]) is int else None
        try:
            score = Decimal(str(row.get('score')))
            maximum = Decimal(str(row.get('max_score')))
            numeric = score.is_finite() and maximum.is_finite() and maximum > 0
        except InvalidOperation:
            numeric = False
        eligible = (row.get('section') == 'notebooks' and row.get('state') == 'completed'
            and row.get('document_id') is not None and row.get('selected_id') is not None
            and type(row.get('class_id')) is int and grade is not None and numeric)
        if not eligible:
            output.append(row)
            continue
        # Never merge separate documents, subjects, scales, states or conclusions.
        identity = (row['document_id'], row['selected_id'], row.get('teacher_id'),
            row.get('subject_id'), row.get('code'), grade, maximum, (row.get('note') or '').strip())
        group = groups.get(identity)
        if group is None:
            group = dict(row=row, scores=[], classes=[], class_ids=[])
            groups[identity] = group
            output.append(row)
        group['scores'].append(score)
        group['classes'].append(source['class_name'])
        group['class_ids'].append(source['class_id'])
    for group in groups.values():
        if len(group['scores']) < 2:
            continue
        row = group['row']
        mean = (sum(group['scores']) / len(group['scores'])).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        row.update(class_name=', '.join(group['classes']), class_id=None,
            class_ids=group['class_ids'], class_count=len(group['scores']),
            score=format(mean, 'f').rstrip('0').rstrip('.') if mean else '0',
            is_average=True)
    return output
