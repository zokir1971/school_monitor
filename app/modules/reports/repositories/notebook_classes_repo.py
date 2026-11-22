"""Scoped teaching load and class headcounts in one bounded Core query."""
from sqlalchemy import and_, distinct, func, or_, select
from app.modules.education.models import (
    SchoolClass, SchoolClassSubjectTeacher, SchoolStudentEnrollment, Subject,
)
from app.modules.staff.models_staff_school import SchoolStaffMember


async def class_options(db, *, school_id, teacher_id, year, as_of, bounds):
    c = SchoolClass.__table__
    t = SchoolClassSubjectTeacher.__table__
    e = SchoolStudentEnrollment.__table__
    s = Subject.__table__
    teacher = SchoolStaffMember.__table__
    counts = (select(e.c.school_class_id, func.count(distinct(e.c.student_id)).label('students'))
        .where(e.c.school_id == school_id, e.c.enrolled_at <= as_of,
               or_(e.c.left_at.is_(None), e.c.left_at >= as_of))
        .group_by(e.c.school_class_id).subquery())
    q = (select(c.c.id.label('class_id'), c.c.grade_level, c.c.letter,
                s.c.id.label('subject_id'), s.c.name_ru, s.c.name_kz,
                func.coalesce(counts.c.students, 0).label('students'))
         .select_from(t.join(c, and_(c.c.id == t.c.school_class_id, c.c.school_id == t.c.school_id))
                      .join(s, s.c.id == t.c.subject_id)
                      .join(teacher, and_(teacher.c.id == t.c.staff_member_id, teacher.c.school_id == t.c.school_id))
                      .outerjoin(counts, counts.c.school_class_id == c.c.id))
         .where(t.c.school_id == school_id, t.c.staff_member_id == teacher_id,
                teacher.c.is_active.is_(True), c.c.academic_year_start == year,
                c.c.is_active.is_(True), or_(t.c.assigned_at.is_(None), t.c.assigned_at <= as_of),
                or_(and_(t.c.unassigned_at.is_(None), t.c.is_active.is_(True)), t.c.unassigned_at > as_of)))
    if bounds.get('version') == 2:
        q = q.where(c.c.id.in_(bounds.get('class_ids') or []))
        if bounds.get('subject_ids'):
            q = q.where(s.c.id.in_(bounds['subject_ids']))
    q = q.distinct().order_by(s.c.id, c.c.grade_level, c.c.letter, c.c.id).limit(501)
    rows = (await db.execute(q)).mappings().all()
    if len(rows) > 500:
        raise ValueError('Уточните область проверки тетрадей.')
    pairs = bounds.get('subject_class_pairs') if bounds.get('version') == 2 else None
    allowed = {(p['subject_id'], p['class_id']) for p in pairs} if pairs is not None else None
    return [dict(row, key=f"{row['class_id']}:{row['subject_id']}",
                 class_name=str(row['grade_level']) + (row['letter'] or ''))
            for row in rows if allowed is None or (row['subject_id'], row['class_id']) in allowed]
