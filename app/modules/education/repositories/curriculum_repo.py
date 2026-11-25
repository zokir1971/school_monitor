
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy import select
from app.modules.education.models import (CurriculumSubjectRule, SubjectMethodProfile, SchoolClassSubject,
                                          SchoolSubjectSubgroup, SchoolSubjectSubgroupMember, SchoolClassSubjectTeacher,
                                          SchoolStudentEnrollment, SchoolStudent, SchoolClass)


@dataclass(frozen=True, slots=True)
class CurriculumStudent:
    """Only the student fields consumed by subgroup allocation and its page."""
    id: int
    last_name: str
    first_name: str
    middle_name: str | None

    @property
    def full_name(self) -> str:
        return ' '.join(part.strip() for part in (self.last_name,self.first_name,self.middle_name)
                        if part and part.strip())


class CurriculumRepo:
    @staticmethod
    async def rules(db):
        return list(
            (await db.execute(select(CurriculumSubjectRule).order_by(CurriculumSubjectRule.id))).scalars().all())

    @staticmethod
    async def profiles(db):
        return list(
            (await db.execute(select(SubjectMethodProfile).order_by(SubjectMethodProfile.name))).scalars().all())

    @staticmethod
    async def school_state(db, school_id, year):
        ids = select(SchoolClass.id).where(SchoolClass.school_id == school_id, SchoolClass.academic_year_start == year)
        offers = list((await db.execute(select(SchoolClassSubject).where(SchoolClassSubject.school_id == school_id,
                                                                         SchoolClassSubject.school_class_id.in_(
                                                                             ids)))).scalars().all())
        groups = list((await db.execute(
            select(SchoolSubjectSubgroup).where(SchoolSubjectSubgroup.school_id == school_id,
                                                SchoolSubjectSubgroup.school_class_id.in_(ids)))).scalars().all())
        offer_ids = select(SchoolClassSubject.id).where(
            SchoolClassSubject.school_id == school_id, SchoolClassSubject.school_class_id.in_(ids))
        members = list((await db.execute(
            select(SchoolSubjectSubgroupMember).where(SchoolSubjectSubgroupMember.school_id == school_id,
                                                      SchoolSubjectSubgroupMember.class_subject_id.in_(offer_ids),
                                                      SchoolSubjectSubgroupMember.is_active.is_(
                                                          True)))).scalars().all()) if offers else []
        roster = list((await db.execute(
            select(SchoolStudentEnrollment.school_class_id, SchoolStudent.id, SchoolStudent.last_name,
                   SchoolStudent.first_name, SchoolStudent.middle_name).join(SchoolStudent, (
                    SchoolStudent.id == SchoolStudentEnrollment.student_id) & (
                    SchoolStudent.school_id == school_id)).where(
                SchoolStudentEnrollment.school_id == school_id, SchoolStudentEnrollment.school_class_id.in_(ids),
                SchoolStudentEnrollment.is_active.is_(True), SchoolStudent.is_active.is_(True)))).all())
        roster = [(cid,CurriculumStudent(sid,last,first,middle)) for cid,sid,last,first,middle in roster]
        assignments = list((await db.execute(
            select(SchoolClassSubjectTeacher).where(SchoolClassSubjectTeacher.school_id == school_id,
                                                    SchoolClassSubjectTeacher.school_class_id.in_(ids),
                                                    SchoolClassSubjectTeacher.is_active.is_(True)))).scalars().all())
        return offers, groups, members, roster, assignments

    @staticmethod
    async def assignment_state(db, school_id, offer):
        groups = list((await db.execute(select(SchoolSubjectSubgroup).where(
            SchoolSubjectSubgroup.school_id == school_id,
            SchoolSubjectSubgroup.class_subject_id == offer.id,
            SchoolSubjectSubgroup.is_active.is_(True)))).scalars().all())
        assignments = list((await db.execute(select(SchoolClassSubjectTeacher).where(
            SchoolClassSubjectTeacher.school_id == school_id,
            SchoolClassSubjectTeacher.school_class_id == offer.school_class_id,
            SchoolClassSubjectTeacher.subject_id == offer.subject_id,
            SchoolClassSubjectTeacher.is_active.is_(True))
            .order_by(SchoolClassSubjectTeacher.id))).scalars().all())
        return groups, assignments

    @staticmethod
    async def offer(db, school_id, offer_id):
        return (await db.execute(select(SchoolClassSubject)
                                 .where(SchoolClassSubject.school_id == school_id,
                                        SchoolClassSubject.id == offer_id))).scalar_one_or_none()

    @staticmethod
    async def class_offer(db, school_id, class_id, subject_id):
        return (await db.execute(select(SchoolClassSubject).where(SchoolClassSubject.school_id == school_id,
                                                                  SchoolClassSubject.school_class_id == class_id,
                                                                  SchoolClassSubject.subject_id == subject_id,
                                                                  SchoolClassSubject.is_active.is_(
                                                                      True)))).scalar_one_or_none()

    @staticmethod
    def add_many(db, rows):
        db.add_all(list(rows))

    @staticmethod
    async def flush(db):
        await db.flush()

    @staticmethod
    async def refresh_actor(db, user):
        await db.refresh(user)

    @staticmethod
    async def class_assignment_state(db,school_id,class_id):
        """Bounded class reads; no pupil roster and no query per subject."""
        offers=list((await db.scalars(select(SchoolClassSubject).where(
            SchoolClassSubject.school_id==school_id,SchoolClassSubject.school_class_id==class_id,
            SchoolClassSubject.is_active.is_(True)))).all())
        groups=list((await db.scalars(select(SchoolSubjectSubgroup).where(
            SchoolSubjectSubgroup.school_id==school_id,SchoolSubjectSubgroup.school_class_id==class_id,
            SchoolSubjectSubgroup.is_active.is_(True)))).all())
        assignments=list((await db.scalars(select(SchoolClassSubjectTeacher).where(
            SchoolClassSubjectTeacher.school_id==school_id,SchoolClassSubjectTeacher.school_class_id==class_id,
            SchoolClassSubjectTeacher.is_active.is_(True)).order_by(SchoolClassSubjectTeacher.id))).all())
        return offers,groups,assignments
