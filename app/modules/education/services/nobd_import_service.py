from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone, timedelta

from app.modules.education.helpers.nobd_language_policy import resolve_language
from app.modules.education.helpers.subgroup_policy import infer_language
from app.modules.education.models import SchoolClass, SchoolStudent, SchoolStudentEnrollment
from app.modules.education.repositories.enrollment_repo import SchoolStudentEnrollmentRepo
from app.modules.education.repositories.school_class_repo import SchoolClassRepo
from app.modules.education.repositories.school_scope_repo import SchoolScopeRepo
from app.modules.education.repositories.student_repo import SchoolStudentRepo
from app.modules.education.services.class_curriculum_service import ClassCurriculumService


class NobdImportService:
    @staticmethod
    async def get_school_name(db, *, school_id: int) -> str:
        name = await SchoolScopeRepo.get_name(db, school_id=school_id)
        if name is None:
            raise ValueError("Мектеп табылмады.")
        return name

    @staticmethod
    async def snapshot(db, school_id, year, data):
        classes = await SchoolClassRepo.get_all_by_school(db, school_id=school_id)
        students = await SchoolStudentRepo.get_all_by_school(db, school_id=school_id)
        enrollments = await SchoolStudentEnrollmentRepo.get_all_active_by_school(db, school_id=school_id)
        cm = {f'{c.grade_level}:{c.letter}': c for c in classes if c.academic_year_start == year}
        sm = {s.iin: s for s in students if s.iin}
        em = {e.student_id: e for e in enrollments}
        all_classes = {c.id: c for c in classes}
        counters = dict(class_languages_saved=0, new_students=0, updated_students=0, unchanged_students=0,
                        new_classes=0, moved_students=0, existing_students=len(students))
        for g in data['groups']:
            c = cm.get(g['key'])
            g['saved_track'] = c.education_track if c else None
            g['saved_language'] = c.instruction_language if c else None
            g['inferred_language'] = infer_language(g['languages'])
            g['existing'] = c is not None
            counters['new_classes'] += c is None
        for r in data['rows']:
            s = sm.get(r['iin'])
            if s is None:
                counters['new_students'] += 1
                continue
            changed = not s.is_active or any(str(getattr(s, k) or '') != str(r[k] or '')
                                             for k in ['last_name', 'first_name', 'middle_name', 'birth_date'])
            counters['updated_students' if changed else 'unchanged_students'] += 1
            e = em.get(s.id)
            target = cm.get(r['key'])
            if e and (not target or e.school_class_id != target.id):
                old = all_classes[e.school_class_id]
                if old.academic_year_start > year:
                    raise ValueError('Нельзя заменить текущее зачисление импортом прошлого учебного года.')
                counters['moved_students'] += 1
        state = [[c.id, str(c.updated_at), c.is_active, c.education_track, c.instruction_language] for c in classes]
        state += [[s.id, str(s.updated_at), s.is_active] for s in students]
        state += [[e.id, e.school_class_id, str(e.updated_at)] for e in enrollments]
        fingerprint = hashlib.sha256(json.dumps(sorted(state, key=str)).encode()).hexdigest()
        return counters, fingerprint, cm, sm, em

    @classmethod
    async def apply(cls, db, school_id, year, data, tracks, confirm_tracks, expected, languages=None,
                    confirm_languages=False):
        # Serialize imports for this school, including imports in different years.
        await SchoolScopeRepo.lock_import(db, school_id=school_id)
        counters, fingerprint, cm, sm, em = await cls.snapshot(db, school_id, year, data)
        if fingerprint != expected:
            raise ValueError('Данные школы изменились после предпросмотра. Загрузите файл повторно.')
        languages = languages or {}
        new_classes = []
        for g in data['groups']:
            track = tracks.get(g['key']) if g['grade'] in (10, 11) else None
            if g['grade'] in (10, 11) and track not in ('emn', 'ogn'):
                raise ValueError('Выберите ЕМН или ОГН для каждого 10–11 класса.')
            c = cm.get(g['key'])
            language = resolve_language(g['languages'], languages.get(g['key']),
                                        c.instruction_language if c else None, confirm_languages)
            if c and c.education_track != track and c.education_track and not confirm_tracks:
                raise ValueError('Подтвердите изменение ранее сохранённого направления.')
            if c is None:
                c = SchoolClass(school_id=school_id, academic_year_start=year, grade_level=g['grade'],
                                letter=g['letter'], is_active=True)
                new_classes.append(c)
                cm[g['key']] = c
            counters['class_languages_saved'] += c.instruction_language != language
            c.instruction_language = language
            c.education_track = track
            c.is_active = True
        SchoolClassRepo.add_many(db, new_classes)
        await SchoolClassRepo.flush(db)
        new_students = []
        now = datetime.now(timezone.utc)
        for r in data['rows']:
            s = sm.get(r['iin'])
            if s is None:
                s = SchoolStudent(school_id=school_id, iin=r['iin'])
                new_students.append(s)
                sm[r['iin']] = s
            for k in ['last_name', 'first_name', 'middle_name']:
                setattr(s, k, r[k])
            s.birth_date = date.fromisoformat(r['birth_date']) if r['birth_date'] else None
            s.is_active = True
            s.last_imported_at = now
        SchoolStudentRepo.add_many(db, new_students)
        await SchoolStudentRepo.flush(db)
        pending = []
        start = date(year, 9, 1)
        for r in data['rows']:
            s, target = sm[r['iin']], cm[r['key']]
            e = em.get(s.id)
            if e and e.school_class_id == target.id:
                continue
            effective = start
            if e:
                # Same-year transfers are dated today; never overlap date intervals.
                effective = max(start, date.today(), e.enrolled_at + timedelta(days=1))
                e.left_at = effective - timedelta(days=1)
                e.is_active = False
            pending.append((s.id, target.id, effective))
        # Close old rows before inserting new ones (partial unique index).
        await SchoolStudentEnrollmentRepo.flush(db)
        SchoolStudentEnrollmentRepo.add_many(
            db,
            [SchoolStudentEnrollment(
                school_id=school_id,
                student_id=s,
                school_class_id=c,
                enrolled_at=d, is_active=True)
                for s, c, d in pending])
        await SchoolStudentEnrollmentRepo.flush(db)
        counters['curriculum'] = await ClassCurriculumService.sync(db, school_id, year)
        return counters
