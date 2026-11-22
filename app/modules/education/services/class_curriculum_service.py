from app.modules.education.repositories.teacher_choices_repo import TeacherChoicesRepo
from app.modules.education.helpers.teacher_subject_choices import build_teacher_choices
from sqlalchemy import select
from datetime import date, datetime, timezone
from app.modules.education.helpers.curriculum_policy import (
    validate_rule,
    expand_languages,
    POLICIES,
    canonical_role,
    supports_all_languages,
    ALL_LANGUAGES,
)
from app.modules.education.repositories.subject_category_repo import SubjectCategoryRepo
from app.modules.education.models import (
    CurriculumSubjectRule, SubjectMethodProfile,
    SchoolClassSubject,
    SchoolSubjectSubgroup,
    SchoolSubjectSubgroupMember,
    SchoolClassSubjectTeacher,
)
from app.modules.education.repositories.curriculum_repo import CurriculumRepo as Repo
from app.modules.education.repositories.school_class_repo import SchoolClassRepo
from app.modules.education.repositories.subject_repo import SubjectRepo
from app.modules.education.repositories.school_scope_repo import SchoolScopeRepo
from app.modules.staff.staff_repo import SchoolStaffRepo
from app.modules.education.helpers.subgroup_policy import LANGUAGES, distribute

ROLES = {
    'literacy': 'Обучение грамоте (1 класс)',
    'literary_reading': 'Литературное чтение (2–4)',
    'native_language': 'Узбекский / уйгурский / таджикский язык',
    'native_literature': 'Узбекская / уйгурская / таджикская литература',
    'general': 'Другой предмет',
    'kz_language': 'Казахский язык',
    'kz_literature': 'Казахская литература',
    'kz_combined': 'Казахский язык и литература',
    'ru_language': 'Русский язык',
    'ru_literature': 'Русская литература',
    'ru_combined': 'Русский язык и литература',
    'english': 'Английский язык',
    'mathematics': "Математика",
    'informatics': 'Информатика',
    'natural_science': 'Естествознание',
    'physics': 'Физика',
    'chemistry': 'Химия',
    'biology': 'Биология',
    'geography': 'География',
}


def year_valid(year):
    if not isinstance(year, int) or not 2000 <= year <= 2100:
        raise ValueError('Учебный год должен быть от 2000 до 2100.')


class ClassCurriculumService:
    @staticmethod
    async def reference_page(db):
        rules = await Repo.rules(db)
        rule_errors = {}
        for rule in rules:
            try:
                validate_rule(rule.instruction_language, rule.grade_level, rule.grade_level, rule.subject_role,
                              rule.split_threshold)
            except ValueError as exc:
                rule_errors[rule.id] = str(exc)
        subjects = await SubjectCategoryRepo.subjects(db)
        subject_map = {subject['id']: subject for subject in subjects}
        for rule in rules:
            subject = subject_map.get(rule.subject_id)
            if subject and (subject['category_id'] is None or subject['curriculum_role'] not in POLICIES):
                rule_errors.setdefault(rule.id, 'Задайте категорию и правила преподавания в справочнике предметов.')
            elif subject and canonical_role(rule.subject_role) != subject['curriculum_role']:
                rule_errors.setdefault(rule.id, 'Правило отличается от настроек предмета. Проверьте справочник.')
        categories = await SubjectCategoryRepo.list_all(db)
        category_by_id = {c['id']: c for c in categories}
        for subject in subjects:
            category = category_by_id.get(subject['category_id'])
            subject['all_languages_allowed'] = (
                category is not None and subject['curriculum_role'] in POLICIES
                and supports_all_languages(subject['curriculum_role'], category['code'])
            )
        return dict(policy_labels=POLICIES, categories=categories, category_by_id={c['id']: c for c in categories},
                    subject_by_id={s['id']: s for s in subjects}, rules=rules, rule_errors=rule_errors,
                    profiles=await Repo.profiles(db),
                    subjects=subjects, languages=LANGUAGES,
                    rule_languages=dict(LANGUAGES, uz_ug_tg='Узбекский / уйгурский / таджикский'), roles=ROLES)

    @staticmethod
    async def subject_policy(db, subject_id):
        subject = await SubjectRepo.get_active_by_id(db, subject_id=subject_id)
        if subject is None:
            raise ValueError('Предмет не найден или неактивен.')
        if subject.category_id is None or subject.curriculum_role not in POLICIES:
            raise ValueError('Сначала задайте категорию и правила преподавания в справочнике предметов.')
        return subject.curriculum_role

    @staticmethod
    async def save_profile(db, code, name):
        import re
        code = code.strip()
        name = name.strip()
        if not re.fullmatch('[a-z0-9_-]{1,80}', code) or not name or len(name) > 255:
            raise ValueError('Заполните код МО (латинские буквы, цифры, _ или -) и название.')
        await SchoolScopeRepo.lock_import(db, school_id=0)
        profiles = await Repo.profiles(db)
        p = next((p for p in profiles if p.code == code), None)
        if p:
            p.name = name
        else:
            Repo.add_many(db, [SubjectMethodProfile(code=code, name=name)])
        await Repo.flush(db)

    @classmethod
    async def save_rule_set(cls, db, language, grade_from, grade_to, track, subject_id, profile_id,
                            split_threshold=None):
        # The web route commits after every selected language has been saved.
        await SchoolScopeRepo.lock_import(db, school_id=0)
        role = await cls.subject_policy(db, subject_id)
        allow_all = False
        if language == ALL_LANGUAGES:
            subject = await SubjectRepo.get_active_by_id(db, subject_id=subject_id)
            category = await SubjectCategoryRepo.get(db, subject.category_id)
            allow_all = category is not None and supports_all_languages(role, category['code'])
        selected = expand_languages(language, allow_all=allow_all)
        for code in selected:
            validate_rule(code, grade_from, grade_to, role, split_threshold)
        for code in selected:
            await cls.save_rule(db, code, grade_from, grade_to, track, subject_id, profile_id, split_threshold)

    @staticmethod
    async def save_rule(db, language, grade_from, grade_to, track, subject_id, profile_id, split_threshold=None):
        await SchoolScopeRepo.lock_import(db, school_id=0)
        role = await ClassCurriculumService.subject_policy(db, subject_id)
        if language not in LANGUAGES or role not in POLICIES or not 1 <= grade_from <= grade_to <= 11:
            raise ValueError('Проверьте язык, предмет и диапазон классов.')
        if track not in ('', 'emn', 'ogn') or (track and (grade_from < 10 or grade_to > 11)):
            raise ValueError('ЕМН/ОГН допускается только для 10–11 классов.')
        validate_rule(language, grade_from, grade_to, role, split_threshold)
        subject = await SubjectRepo.get_active_by_id(db, subject_id=subject_id)
        if subject is None:
            raise ValueError('Предмет не найден или неактивен.')
        if profile_id and not any(p.id == profile_id for p in await Repo.profiles(db)):
            raise ValueError('Профиль МО не найден.')
        await SchoolScopeRepo.lock_import(db, school_id=0)
        rules = await Repo.rules(db)
        if any(r.subject_id == subject_id and canonical_role(r.subject_role) != role for r in rules):
            raise ValueError(
                'Для этого предмета уже задан другой тип. Используйте соответствующий отдельный предмет справочника.')
        threshold = split_threshold
        added = []
        for grade in range(grade_from, grade_to + 1):
            r = next((r for r in rules if (r.instruction_language, r.grade_level, r.education_track, r.subject_id) == (
                language, grade, track, subject_id)), None)
            if r is None:
                r = CurriculumSubjectRule(instruction_language=language, grade_level=grade, education_track=track,
                                          subject_id=subject_id)
                added.append(r)
            r.subject_role = role
            r.method_profile_id = profile_id
            r.split_threshold = threshold
            r.is_active = True
        Repo.add_many(db, added)
        await Repo.flush(db)

    @staticmethod
    async def edit_rule(db, rule_id, language, grade, track, subject_id, profile_id, split_threshold, is_active):
        await SchoolScopeRepo.lock_import(db, school_id=0)
        role = await ClassCurriculumService.subject_policy(db, subject_id)
        if language not in LANGUAGES or role not in POLICIES:
            raise ValueError('Выберите язык и тип предмета.')
        if track not in ('', 'emn', 'ogn') or (track and grade not in (10, 11)):
            raise ValueError('ЕМН/ОГН допускается только для 10–11 классов.')
        validate_rule(language, grade, grade, role, split_threshold)
        await SchoolScopeRepo.lock_import(db, school_id=0)
        rules = await Repo.rules(db)
        rule = next((r for r in rules if r.id == rule_id), None)
        if rule is None:
            raise ValueError('Правило не найдено. Обновите страницу.')
        if await SubjectRepo.get_active_by_id(db, subject_id=subject_id) is None:
            raise ValueError('Предмет не найден или неактивен.')
        if profile_id and not any(p.id == profile_id for p in await Repo.profiles(db)):
            raise ValueError('Профиль МО не найден.')
        key = (language, grade, track, subject_id)
        if any(r.id != rule_id and (r.instruction_language, r.grade_level, r.education_track or '', r.subject_id) == key
               for r in rules):
            raise ValueError(
                'Такое правило уже существует, включая отключённые записи. Редактируйте существующее правило.')
        if any(r.id != rule_id and r.subject_id == subject_id
               and canonical_role(r.subject_role) != role for r in rules):
            raise ValueError(
                'Для предмета в других правилах задан иной тип. Исправьте согласованность типов перед сохранением.')
        rule.instruction_language = language
        rule.grade_level = grade
        rule.education_track = track
        rule.subject_id = subject_id
        rule.subject_role = role
        rule.method_profile_id = profile_id
        rule.split_threshold = split_threshold
        rule.is_active = is_active
        await Repo.flush(db)

    @staticmethod
    async def delete_rule(db, rule_id):
        await SchoolScopeRepo.lock_import(db, school_id=0)
        rule = next((r for r in await Repo.rules(db) if r.id == rule_id), None)
        if rule is None:
            raise ValueError('Правило не найдено. Обновите страницу.')
        linked_id = (await db.execute(
            select(SchoolClassSubject.id)
            .where(SchoolClassSubject.rule_id == rule_id)
            .limit(1)
        )).scalar_one_or_none()
        if linked_id is not None:
            raise ValueError(
                'Удаление невозможно: правило связано с предметами классов, включая неактивные. Исправьте или '
                'отключите правило.')
        await db.delete(rule)
        await Repo.flush(db)

    @staticmethod
    async def deactivate_rule(db, rule_id):
        await SchoolScopeRepo.lock_import(db, school_id=0)
        rule = next((r for r in await Repo.rules(db) if r.id == rule_id), None)
        if rule is None:
            raise ValueError('Правило не найдено.')
        rule.is_active = False
        await Repo.flush(db)

    @classmethod
    async def set_language(cls, db, school_id, class_id, language):
        if language not in LANGUAGES:
            raise ValueError('Выберите язык обучения.')
        await SchoolScopeRepo.lock_import(db, school_id=school_id)
        c = await SchoolClassRepo.get_by_id_for_school(db, class_id=class_id, school_id=school_id)
        if c is None or not c.is_active:
            raise ValueError('Активный класс вашей школы не найден.')
        c.instruction_language = language
        await SchoolClassRepo.flush(db)
        return await cls.sync(db, school_id, c.academic_year_start)

    @classmethod
    async def sync(cls, db, school_id, year):
        year_valid(year)
        await SchoolScopeRepo.lock_import(db, school_id=school_id)
        # Same lock order as NOBD import: school, then reference configuration.
        await SchoolScopeRepo.lock_import(db, school_id=0)
        classes = await SchoolClassRepo.get_active_by_school_and_year(db, school_id=school_id, academic_year_start=year)
        rules = [r for r in await Repo.rules(db) if r.is_active]
        for rule in rules:
            try:
                validate_rule(rule.instruction_language, rule.grade_level, rule.grade_level, rule.subject_role,
                              rule.split_threshold)
            except ValueError as exc:
                raise ValueError(f'Исправьте правило №{rule.id} в справочнике супер админа: {exc}') from exc
        active_subjects = {s.id for s in await SubjectRepo.get_active_all(db)}
        offers, groups, members, roster, assignments = await Repo.school_state(db, school_id, year)
        students_by_class = {c.id: [] for c in classes}
        for cid, s in roster:
            if cid in students_by_class:
                students_by_class[cid].append(s)
        lookup = {(o.school_class_id, o.subject_id): o for o in offers}
        desired = {}
        warnings = []
        created = []
        for c in classes:
            if not c.instruction_language:
                warnings.append(f'{c.name}: укажите язык обучения.')
                continue
            applicable = [r for r in rules if
                          r.instruction_language == c.instruction_language and r.grade_level == c.grade_level
                          and r.education_track in (
                              '', c.education_track or '') and r.subject_id in active_subjects]
            if not applicable:
                for o in offers:
                    if o.school_class_id == c.id:
                        o.is_active = False
                warnings.append(f'{c.name}: для языка и параллели нет активного набора предметов.')
                continue
            chosen = {}
            for r in sorted(applicable, key=lambda r: bool(r.education_track)):
                chosen[r.subject_id] = r
            for r in chosen.values():
                o = lookup.get((c.id, r.subject_id))
                if o is None:
                    o = SchoolClassSubject(school_id=school_id, school_class_id=c.id, subject_id=r.subject_id,
                                           rule_id=r.id, is_active=True, split_enabled=False)
                    created.append(o)
                    lookup[(c.id, r.subject_id)] = o
                o.rule_id = r.id
                o.is_active = True
                desired[(c.id, r.subject_id)] = (
                    o, r.split_threshold is not None and len(students_by_class[c.id]) >= r.split_threshold)
            for o in offers:
                if o.school_class_id == c.id and o.subject_id not in chosen:
                    o.is_active = False
        Repo.add_many(db, created)
        await Repo.flush(db)
        offers += created
        active_class_ids = {c.id for c in classes}
        for o in offers:
            if o.school_class_id not in active_class_ids:
                o.is_active = False
        group_map = {(g.class_subject_id, g.number): g for g in groups}
        new_groups = []
        for o, split in desired.values():
            o.split_enabled = split
            if split:
                for number in (1, 2):
                    g = group_map.get((o.id, number))
                    if g is None:
                        g = SchoolSubjectSubgroup(class_subject_id=o.id, school_id=school_id,
                                                  school_class_id=o.school_class_id, subject_id=o.subject_id,
                                                  number=number, is_active=True)
                        new_groups.append(g)
                        group_map[(o.id, number)] = g
                    g.is_active = True
        Repo.add_many(db, new_groups)
        await Repo.flush(db)
        groups += new_groups
        group_ids = {g.id: g for g in groups}
        now = datetime.now(timezone.utc)
        new_members = []
        for o in offers:
            # Unconfigured classes remain untouched.
            if (o.school_class_id, o.subject_id) not in desired and o.is_active:
                continue
            active = [m for m in members if m.class_subject_id == o.id and m.is_active]
            split = o.is_active and o.split_enabled
            for g in groups:
                if g.class_subject_id == o.id:
                    g.is_active = split
            allocation = {}
            if split:
                previous = {m.student_id: group_ids[m.subgroup_id].number for m in active}
                allocation = distribute(students_by_class.get(o.school_class_id, []), previous)
            kept = set()
            for m in active:
                target = allocation.get(m.student_id)
                if target and group_ids[m.subgroup_id].number == target:
                    kept.add(m.student_id)
                else:
                    m.is_active = False
                    m.left_at = now
            for sid, number in allocation.items():
                if sid not in kept:
                    new_members.append(
                        SchoolSubjectSubgroupMember(class_subject_id=o.id, subgroup_id=group_map[(o.id, number)].id,
                                                    school_id=school_id, student_id=sid, joined_at=now, is_active=True))
            for a in assignments:
                if (a.school_class_id, a.subject_id) != (o.school_class_id, o.subject_id):
                    continue
                wrong = (split and a.subgroup_id is None) or (
                        not split and a.subgroup_id is not None) or not o.is_active
                if wrong:
                    a.is_active = False
                    a.unassigned_at = date.today()
                    warnings.append(
                        f'Класс №{o.school_class_id}, предмет №{o.subject_id}: назначение закрыто из-за изменения '
                        f'режима, назначьте учителей заново.')
        await Repo.flush(db)
        Repo.add_many(db, new_members)
        await Repo.flush(db)
        return dict(new_subjects=len(created), new_members=len(new_members), warnings=list(dict.fromkeys(warnings)))

    @classmethod
    async def page(cls, db, school_id, year):
        year_valid(year)
        name = await SchoolScopeRepo.get_name(db, school_id=school_id)
        if name is None:
            raise ValueError('Школа не найдена.')
        classes = await SchoolClassRepo.get_active_by_school_and_year(db, school_id=school_id, academic_year_start=year)
        subjects = {s.id: s for s in await SubjectRepo.get_active_all(db)}
        rules = {r.id: r for r in await Repo.rules(db)}
        profiles = {p.id: p for p in await Repo.profiles(db)}
        offers, groups, members, roster, assignments = await Repo.school_state(db, school_id, year)
        teachers = list(await TeacherChoicesRepo.list_active(db, school_id=school_id))
        class_map = {c.id: c for c in classes}
        roster_by = {c.id: [] for c in classes}
        for cid, s in roster:
            if cid in roster_by:
                roster_by[cid].append(s)
        # Index once; do not scan all school memberships for every subgroup.
        groups_by_offer={}
        for group in groups:
            if group.is_active:groups_by_offer.setdefault(group.class_subject_id,[]).append(group)
        member_ids_by_group={}
        for member in members:
            if member.is_active:member_ids_by_group.setdefault(member.subgroup_id,set()).add(member.student_id)
        assignment_by_key={}
        for assignment in assignments:
            if assignment.is_primary:
                assignment_by_key.setdefault((assignment.school_class_id,assignment.subject_id,assignment.subgroup_id),assignment)
        rows = []
        for o in offers:
            if not o.is_active or o.school_class_id not in class_map:
                continue
            subgroup_rows = []
            for g in groups_by_offer.get(o.id,[]):
                ids = member_ids_by_group.get(g.id,set())
                people = sorted([s for s in roster_by[o.school_class_id] if s.id in ids],
                                key=lambda s: (s.last_name, s.first_name, s.id))
                assignment = assignment_by_key.get((o.school_class_id,o.subject_id,g.id))
                subgroup_rows.append(dict(group=g, students=people, assignment=assignment))
            assignment = assignment_by_key.get((o.school_class_id,o.subject_id,None))
            profile = profiles.get(rules[o.rule_id].method_profile_id) if o.rule_id in rules else None
            rows.append(dict(offer=o, school_class=class_map[o.school_class_id], subject=subjects.get(o.subject_id),
                             groups=sorted(subgroup_rows, key=lambda r: r['group'].number), assignment=assignment,
                             profile=profile))
        rows.sort(key=lambda r: (
            r['school_class'].grade_level, r['school_class'].letter, r['subject'].name_kz if r['subject'] else ''))
        rows_by_class = {c.id: [] for c in classes}
        for row in rows:
            rows_by_class[row['school_class'].id].append(row)
        class_blocks = []
        for c in sorted(classes, key=lambda c: (c.grade_level, c.letter or '', c.id)):
            subject_rows = rows_by_class[c.id]
            class_blocks.append(dict(
                school_class=c,
                language_name=LANGUAGES.get(c.instruction_language, 'Язык не указан'),
                student_count=len({student.id for student in roster_by[c.id]}),
                subject_rows=subject_rows,
                subgroup_count=sum(len(row['groups']) for row in subject_rows),
            ))
        return dict(school_name=name, year=year, classes=classes, rows=rows,
                    class_blocks=class_blocks, teachers=teachers, languages=LANGUAGES,
                    teachers_by_id={t.id:t for t in teachers},
                    teacher_choices=build_teacher_choices(teachers, subjects.values(), assignments))

    @staticmethod
    async def assign(db, school_id, offer_id, subgroup_id, staff_id):
        await SchoolScopeRepo.lock_import(db, school_id=school_id)
        offer = await Repo.offer(db, school_id, offer_id)
        if offer is None or not offer.is_active:
            raise ValueError('Предмет вашей школы не найден.')
        c = await SchoolClassRepo.get_by_id_for_school(db, class_id=offer.school_class_id, school_id=school_id)
        if c is None or not c.is_active:
            raise ValueError('Класс неактивен.')
        groups, assignments = await Repo.assignment_state(db, school_id, offer)
        if offer.split_enabled:
            if not any(g.id == subgroup_id and g.class_subject_id == offer.id and g.is_active for g in groups):
                raise ValueError('Выберите подгруппу этого предмета.')
        elif subgroup_id is not None:
            raise ValueError('Предмет ведётся всем классом.')
        teacher = await TeacherChoicesRepo.get_active(db, school_id=school_id, staff_member_id=staff_id)
        if teacher is None:
            raise ValueError('Активный сотрудник вашей школы не найден.')
        current = [a for a in assignments if
                   a.school_class_id == c.id and a.subject_id == offer.subject_id and a.subgroup_id == subgroup_id
                   and a.is_primary]
        if len(current) == 1 and current[0].staff_member_id == staff_id:
            return
        for a in current:
            a.is_active = False
            a.unassigned_at = date.today()
        await Repo.flush(db)
        existing = next((a for a in assignments if
                         a.is_active and a.school_class_id == c.id and a.subject_id == offer.subject_id
                         and a.subgroup_id == subgroup_id and a.staff_member_id == staff_id),
                        None)
        if existing:
            existing.is_primary = True
            await Repo.flush(db)
            return
        Repo.add_many(db, [
            SchoolClassSubjectTeacher(school_id=school_id, school_class_id=c.id, subject_id=offer.subject_id,
                                      subgroup_id=subgroup_id, staff_member_id=staff_id,
                                      teacher_name_snapshot=teacher.full_name, is_primary=True, is_active=True,
                                      assigned_at=date.today())])
        await Repo.flush(db)
