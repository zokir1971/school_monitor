"""School report layouts contain reusable criteria, never class IDs from another year."""
from collections import defaultdict

SUPPORTED = {'knowledge_quality_table', 'class_summary'}
MATH_CODES = {'mathematics', 'math', 'algebra', 'algebra_and_analysis', 'algebra_and_calculus'}


def selector(subject_id, school_class):
    return (subject_id, school_class['grade_level'], school_class.get('instruction_language') or '',
            school_class.get('education_track') or '')


def suggestions(catalog, scheme=None):
    """Apply a school layout first; every unmatched pair gets a safe default report."""
    classes = {c['id']: c for c in catalog['classes']}
    subjects = {s['id']: s for s in catalog['subjects']}
    pairs = {(p['subject_id'], p['class_id']) for p in catalog['subject_classes']}
    from app.core.feature_flags import report_enabled
    available = {(code, sid, cid) for code in SUPPORTED if report_enabled(code) for sid, cid in pairs}
    claimed = set()
    result = []
    for rule in (scheme or {}).get('rules', []):
        matchers = {tuple(p) for p in rule['selectors']}
        for code in rule['report_codes']:
            chosen = sorted((sid, cid) for c, sid, cid in available - claimed
                            if c == code and selector(sid, classes[cid]) in matchers)
            if chosen:
                result.append(dict(id=rule['id']+'_'+code, name_ru=rule['name_ru'], name_kk=rule['name_kk'],
                                   report_codes=[code], pairs=[dict(subject_id=s, class_id=c) for s, c in chosen]))
                claimed.update((code, s, c) for s, c in chosen)
    buckets = defaultdict(list)
    for code, sid, cid in sorted(available - claimed):
        grade = classes[cid]['grade_level']
        subject = subjects[sid]
        if grade <= 4:
            key, ru, kk = 'primary', 'Начальная школа, 1–4', 'Бастауыш мектеп, 1–4'
        elif subject.get('code') in MATH_CODES and 5 <= grade <= 11:
            key, ru, kk = 'math', 'Математическое направление, 5–11', 'Математика бағыты, 5–11'
        else:
            key = 'subject_'+str(sid)
            ru, kk = subject.get('name_ru') or subject['name_kz'], subject.get('name_kz') or subject['name_ru']
        buckets[(code, key, ru, kk)].append(dict(subject_id=sid, class_id=cid))
    for (code, key, ru, kk), chosen in buckets.items():
        result.append(dict(id='auto_'+key+'_'+code, name_ru=ru, name_kk=kk, report_codes=[code], pairs=chosen))
    return result


def school_layout(areas, catalog, previous=None):
    """Replace only criteria covered by this task, preserving other school settings."""
    classes = {c['id']: c for c in catalog['classes']}
    changed = defaultdict(set)
    for area in areas:
        for code in area['report_codes']:
            changed[code].update(selector(p['subject_id'], classes[p['class_id']]) for p in area['pairs'])
    rules = []
    for rule in (previous or {}).get('rules', []):
        for code in rule['report_codes']:
            remaining = [p for p in rule['selectors'] if tuple(p) not in changed[code]]
            if remaining:
                rules.append(dict(rule, report_codes=[code], selectors=remaining))
    for number, area in enumerate(areas):
        criteria = sorted({selector(p['subject_id'], classes[p['class_id']]) for p in area['pairs']})
        rules.append(dict(id='layout_'+str(number)+'_'+area['id'][:24], name_ru=area['name_ru'],
                          name_kk=area['name_kk'], report_codes=area['report_codes'], selectors=[list(p) for p in criteria]))
    if len(rules) > 100:
        raise ValueError('Уменьшите количество областей школьной схемы. / Мектеп сызбасындағы ауқымдар санын азайтыңыз.')
    # Two class-specific areas may collapse to the same future grade/language/track.
    occupied = set()
    for rule in rules:
        for code in rule['report_codes']:
            for pattern in rule['selectors']:
                key = (code, *pattern)
                if key in occupied:
                    raise ValueError('Школьная схема пересекается по предмету, параллели, языку и профилю. Сохраните алгоритм без сохранения школьной схемы либо объедините такие области. / Мектеп сызбасында пән, сынып деңгейі, тіл және бейін қайталанады. Алгоритмді мектеп сызбасын сақтамай сақтаңыз немесе осындай ауқымдарды біріктіріңіз.')
                occupied.add(key)
    # Template rule IDs are internal; report target IDs remain in the task itself.
    for number, rule in enumerate(rules):
        rule['id'] = 'school_rule_'+str(number)
    return dict(version=1, rules=rules)
