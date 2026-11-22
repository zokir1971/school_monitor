"""Subject recommendations from staff profile text and current assignments.

Recommendations do not replace school/active checks when an assignment is saved.
Unknown or incomplete profile text can be handled with the explicit full-list UI.
"""
import re
import unicodedata

PATTERNS = {
    'physics': r'физик|physics|фізик',
    'mathematics': r'математ|алгебр|геометр|mathematics|\bmath\b',
    'informatics': r'информат|цифрл|цифров|ақпараттық|computer science|informatics|digital literacy',
    'chemistry': r'хими|chemistry',
    'biology': r'биолог|biology',
    'geography': r'географ|geography',
    'history': r'тарих|истори|history',
    'kz': r'қазақ|казах|kazakh',
    'ru': r'орыс|русск|russian',
    'uz': r'өзбек|узбек|uzbek',
    'uyg': r'ұйғыр|уйгур|uyghur|uighur',
    'taj': r'тәжік|таджик|tajik',
    'english': r'ағылшын|англий|english',
    'physical_education': r'дене шынықтыру|физическ|physical education',
    'music': r'музык|music',
    'natural_science': r'жаратылыстан|естествознан|natural science',
}
MATCHERS = {key: re.compile(pattern) for key, pattern in PATTERNS.items()}
ROLE_FAMILY = {**{key: key for key in ('physics','mathematics','informatics','chemistry','biology','geography','history','natural_science')},
    **{prefix + suffix: prefix for prefix in ('kz','ru') for suffix in ('_language','_literature','_combined')}}

def normalized(value):
    value = unicodedata.normalize('NFKC', str(value or '')).casefold().replace('ё','е')
    return ' '.join(re.findall(r'[^\W_]+', value, flags=re.UNICODE))

def families(text):
    return {key for key, matcher in MATCHERS.items() if matcher.search(text)}

def build_teacher_choices(teachers, subjects, assignments):
    teachers = list(teachers)
    teacher_ids = {teacher.id for teacher in teachers}
    text_by_id = {t.id: normalized(str(t.subject or '') + ' ' + str(t.diploma_specialty or '')) for t in teachers}
    families_by_id = {key: families(value) for key, value in text_by_id.items()}
    assigned = {}
    for assignment in assignments:
        if assignment.is_active and assignment.unassigned_at is None and assignment.staff_member_id in teacher_ids:
            assigned.setdefault(assignment.subject_id, set()).add(assignment.staff_member_id)
    by_subject = {}
    for subject in subjects:
        names = [normalized(subject.name_kz), normalized(subject.name_ru)]
        subject_families = families(' '.join(names))
        role_family = ROLE_FAMILY.get(subject.curriculum_role)
        if role_family: subject_families.add(role_family)
        matching = set(assigned.get(subject.id, ()))
        for teacher in teachers:
            evidence = text_by_id[teacher.id]
            if subject_families:
                matches = bool(subject_families & families_by_id[teacher.id])
            else:
                matches = any(len(name) >= 3 and (' ' + name + ' ') in (' ' + evidence + ' ') for name in names)
            if matches: matching.add(teacher.id)
        by_subject[str(subject.id)] = [t.id for t in teachers if t.id in matching]
    return dict(teachers=[dict(id=t.id, name=t.full_name,
        label=' · '.join(str(v).strip() for v in (t.full_name, t.subject, t.diploma_specialty) if v and str(v).strip())) for t in teachers],
        by_subject=by_subject)
