
from __future__ import annotations
from sqlalchemy import select
from app.modules.education.models import (CurriculumSubjectRule, SubjectMethodProfile, SchoolClassSubject,
                                          SchoolSubjectSubgroup, SchoolSubjectSubgroupMember, SchoolClassSubjectTeacher,
                                          SchoolStudentEnrollment, SchoolStudent, SchoolClass)


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
        offer_ids = [o.id for o in offers]
        members = list((await db.execute(
            select(SchoolSubjectSubgroupMember).where(SchoolSubjectSubgroupMember.school_id == school_id,
                                                      SchoolSubjectSubgroupMember.class_subject_id.in_(offer_ids),
                                                      SchoolSubjectSubgroupMember.is_active.is_(
                                                          True)))).scalars().all()) if offer_ids else []
        roster = list((await db.execute(
            select(SchoolStudentEnrollment.school_class_id, SchoolStudent).join(SchoolStudent, (
                    SchoolStudent.id == SchoolStudentEnrollment.student_id) & (
                    SchoolStudent.school_id == school_id)).where(
                SchoolStudentEnrollment.school_id == school_id, SchoolStudentEnrollment.school_class_id.in_(ids),
                SchoolStudentEnrollment.is_active.is_(True), SchoolStudent.is_active.is_(True)))).all())
        assignments = list((await db.execute(
            select(SchoolClassSubjectTeacher).where(SchoolClassSubjectTeacher.school_id == school_id,
                                                    SchoolClassSubjectTeacher.school_class_id.in_(ids),
                                                    SchoolClassSubjectTeacher.is_active.is_(True)))).scalars().all())
        return offers, groups, members, roster, assignments

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
