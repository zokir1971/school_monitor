# app/modules/education/models.py

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text as sa_text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.modules.org.models import School
    from app.modules.staff.models_staff_school import SchoolStaffMember
    from app.modules.assessment.models import AssessmentBlueprint, QuestionBankItem


# =========================================================
# SUBJECT
# =========================================================


class SubjectCategory(Base):
    """Глобальные категории предметов; управляются через справочник."""
    __tablename__ = 'subject_categories'
    __table_args__ = (UniqueConstraint('code', name='uq_subject_categories_code'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name_kz: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100, server_default='100')


class Subject(Base):
    """
    Глобальный справочник учебных предметов.

    Предметы не принадлежат конкретной школе и могут
    использоваться всеми школами School Monitor.
    """

    __tablename__ = "subjects"

    __table_args__ = (
        Index(
            "ix_subjects_active_sort",
            "is_active",
            "sort_order",
        ),
        Index(
            "ix_subjects_name_kz",
            "name_kz",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey('subject_categories.id', name='fk_subjects_category_id', ondelete='RESTRICT'),
        nullable=True, index=True,
    )
    # NULL marks legacy subjects requiring a deliberate policy choice.
    curriculum_role: Mapped[str | None] = mapped_column(String(30), nullable=True, default='general',
                                                        server_default='general')

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    name_kz: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    name_ru: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default=sa_text("100"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    class_teacher_assignments: Mapped[
        list["SchoolClassSubjectTeacher"]
    ] = relationship(
        "SchoolClassSubjectTeacher",
        back_populates="subject",
        lazy="raise",
    )

    assessment_blueprints: Mapped[
        list["AssessmentBlueprint"]
    ] = relationship(
        "AssessmentBlueprint",
        back_populates="subject",
        lazy="raise",
    )

    question_bank_items: Mapped[
        list["QuestionBankItem"]
    ] = relationship(
        "QuestionBankItem",
        back_populates="subject",
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<Subject id={self.id} "
            f"code={self.code!r} "
            f"name_kz={self.name_kz!r}>"
        )


# =========================================================
# SCHOOL CLASS
# =========================================================


class SchoolClass(Base):
    """
    Класс конкретной школы в конкретном учебном году.

    academic_year_start=2026 означает учебный год 2026/2027.

    9А 2026/2027 и 9А 2027/2028 являются разными
    историческими сущностями.
    """

    __tablename__ = "school_classes"

    __table_args__ = (
        CheckConstraint("instruction_language IS NULL OR instruction_language IN ('kz','ru','uz','tg','ug')",
                        name='ck_school_class_instruction_language'),
        # Нужен как целевой уникальный ключ для составных FK,
        # защищающих границу школы.
        UniqueConstraint(
            "id",
            "school_id",
            name="uq_school_classes_id_school",
        ),
        UniqueConstraint(
            "school_id",
            "academic_year_start",
            "grade_level",
            "letter",
            name="uq_school_class_year_grade_letter",
        ),
        CheckConstraint(
            "academic_year_start >= 2000 "
            "AND academic_year_start <= 2100",
            name="ck_school_class_academic_year",
        ),
        CheckConstraint(
            "grade_level >= 1 AND grade_level <= 12",
            name="ck_school_class_grade_level",
        ),
        CheckConstraint(
            "length(trim(letter)) > 0",
            name="ck_school_class_letter_not_blank",
        ),
        CheckConstraint(
            "education_track IS NULL OR "
            "(grade_level IN (10, 11) AND education_track IN ('emn', 'ogn'))",
            name="ck_school_class_education_track",
        ),
        Index(
            "ix_school_classes_school_year_active",
            "school_id",
            "academic_year_start",
            "is_active",
        ),
        Index(
            "ix_school_classes_school_grade",
            "school_id",
            "grade_level",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    academic_year_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    grade_level: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    letter: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    instruction_language: Mapped[str | None] = mapped_column(String(5), nullable=True)

    education_track: Mapped[str | None] = mapped_column(
        String(10), nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    school: Mapped[School] = relationship(
        "School",
        lazy="raise",
    )

    enrollments: Mapped[list[SchoolStudentEnrollment]] = relationship(
        "SchoolStudentEnrollment",
        back_populates="school_class",
        primaryjoin=(
            "SchoolClass.id == "
            "foreign(SchoolStudentEnrollment.school_class_id)"
        ),
        order_by="SchoolStudentEnrollment.enrolled_at.asc()",
        lazy="raise",
    )

    subject_teachers: Mapped[
        list[SchoolClassSubjectTeacher]
    ] = relationship(
        "SchoolClassSubjectTeacher",
        back_populates="school_class",
        lazy="raise",
    )

    @property
    def name(self) -> str:
        return f"{self.grade_level}{self.letter}"

    @property
    def academic_year_label(self) -> str:
        return (
            f"{self.academic_year_start}/"
            f"{self.academic_year_start + 1}"
        )

    def __repr__(self) -> str:
        return (
            f"<SchoolClass id={self.id} "
            f"school_id={self.school_id} "
            f"name={self.name!r} "
            f"year={self.academic_year_label!r}>"
        )


# =========================================================
# SCHOOL STUDENT
# =========================================================


class SchoolStudent(Base):
    """
    Учащийся школы, загруженный из внешнего источника
    (например НОБД).

    SchoolStudent НЕ является пользователем School Monitor:
    у него нет user_id, логина, пароля и роли.

    Текущий и исторический класс хранится не здесь,
    а в SchoolStudentEnrollment.
    """

    __tablename__ = "school_students"

    __table_args__ = (
        # Нужен как целевой уникальный ключ для составных FK.
        UniqueConstraint(
            "id",
            "school_id",
            name="uq_school_students_id_school",
        ),
        UniqueConstraint(
            "school_id",
            "source_system",
            "external_id",
            name="uq_school_student_external",
        ),
        UniqueConstraint(
            "school_id",
            "iin",
            name="uq_school_student_iin",
        ),
        CheckConstraint(
            "("
            "source_system IS NULL AND external_id IS NULL"
            ") OR ("
            "source_system IS NOT NULL AND external_id IS NOT NULL"
            ")",
            name="ck_school_student_external_pair",
        ),
        CheckConstraint(
            "iin IS NULL OR length(iin) = 12",
            name="ck_school_student_iin_length",
        ),
        Index(
            "ix_school_students_school_active",
            "school_id",
            "is_active",
        ),
        Index(
            "ix_school_students_school_name",
            "school_id",
            "last_name",
            "first_name",
        ),
        Index(
            "ix_school_students_external_id",
            "external_id",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    source_system: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    external_id: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    iin: Mapped[str | None] = mapped_column(
        String(12),
        nullable=True,
    )

    last_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    first_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    middle_name: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    birth_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
    )

    last_imported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    school: Mapped[School] = relationship(
        "School",
        lazy="raise",
    )

    enrollments: Mapped[list[SchoolStudentEnrollment]] = relationship(
        "SchoolStudentEnrollment",
        back_populates="student",
        primaryjoin=(
            "SchoolStudent.id == "
            "foreign(SchoolStudentEnrollment.student_id)"
        ),
        order_by="SchoolStudentEnrollment.enrolled_at.asc()",
        lazy="raise",
    )

    @property
    def full_name(self) -> str:
        parts = (
            self.last_name,
            self.first_name,
            self.middle_name,
        )
        return " ".join(
            part.strip()
            for part in parts
            if part and part.strip()
        )

    def __repr__(self) -> str:
        return (
            f"<SchoolStudent id={self.id} "
            f"school_id={self.school_id} "
            f"full_name={self.full_name!r}>"
        )


# =========================================================
# STUDENT ENROLLMENT
# =========================================================


class SchoolStudentEnrollment(Base):
    """
    История принадлежности ученика к классу.

    Строки истории не удаляются при переходе ученика:
    предыдущая запись закрывается через left_at/is_active,
    а для нового класса создается новая запись.

    school_id намеренно дублируется, чтобы PostgreSQL
    составными FK гарантировал:
        student.school_id == class.school_id == enrollment.school_id.
    """

    __tablename__ = "school_student_enrollments"

    __table_args__ = (
        ForeignKeyConstraint(
            ["student_id", "school_id"],
            [
                "school_students.id",
                "school_students.school_id",
            ],
            name="fk_student_enrollment_student_school",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["school_class_id", "school_id"],
            [
                "school_classes.id",
                "school_classes.school_id",
            ],
            name="fk_student_enrollment_class_school",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "student_id",
            "school_class_id",
            "enrolled_at",
            name="uq_student_enrollment_period_start",
        ),
        CheckConstraint(
            "left_at IS NULL OR left_at >= enrolled_at",
            name="ck_student_enrollment_dates",
        ),
        Index(
            "uq_student_active_enrollment",
            "student_id",
            unique=True,
            postgresql_where=sa_text("is_active = true"),
        ),
        Index(
            "ix_student_enrollments_class_active",
            "school_class_id",
            "is_active",
        ),
        Index(
            "ix_student_enrollments_school_active",
            "school_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    student_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    school_class_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    enrolled_at: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    left_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    student: Mapped[SchoolStudent] = relationship(
        "SchoolStudent",
        back_populates="enrollments",
        primaryjoin=(
            "foreign(SchoolStudentEnrollment.student_id) "
            "== SchoolStudent.id"
        ),
        lazy="raise",
    )

    school_class: Mapped[SchoolClass] = relationship(
        "SchoolClass",
        back_populates="enrollments",
        primaryjoin=(
            "foreign(SchoolStudentEnrollment.school_class_id) "
            "== SchoolClass.id"
        ),
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<SchoolStudentEnrollment id={self.id} "
            f"school_id={self.school_id} "
            f"student_id={self.student_id} "
            f"school_class_id={self.school_class_id} "
            f"is_active={self.is_active}>"
        )


# =========================================================
# CLASS / SUBJECT / TEACHER
# =========================================================


class SchoolClassSubjectTeacher(Base):
    """
    История назначения преподавателя:

        школа + класс + предмет + преподаватель + период.

    Смена учителя, отпуск, декрет или увольнение не удаляют
    старое назначение. Запись закрывается, затем создается новая.

    Граница школы для класса защищена составным FK.
    Принадлежность staff_member той же школе дополнительно
    проверяет сервис, поскольку staff_member_id nullable и
    использует ON DELETE SET NULL для сохранения истории.
    """

    __tablename__ = "school_class_subject_teachers"

    __table_args__ = (
        ForeignKeyConstraint(
            ["school_class_id", "school_id"],
            [
                "school_classes.id",
                "school_classes.school_id",
            ],
            name="fk_class_subject_teacher_class_school",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ['subgroup_id', 'school_class_id', 'subject_id', 'school_id'],
            ['school_subject_subgroups.id', 'school_subject_subgroups.school_class_id',
             'school_subject_subgroups.subject_id', 'school_subject_subgroups.school_id'],
            name='fk_teacher_subgroup_context', ondelete='RESTRICT',
        ),
        CheckConstraint(
            "unassigned_at IS NULL "
            "OR assigned_at IS NULL "
            "OR unassigned_at >= assigned_at",
            name="ck_class_subject_teacher_dates",
        ),
        Index(
            "uq_active_class_subject_teacher",
            "school_class_id",
            "subject_id",
            "staff_member_id",
            sa_text("coalesce(subgroup_id, 0)"),
            unique=True,
            postgresql_where=sa_text(
                "is_active = true "
                "AND staff_member_id IS NOT NULL"
            ),
        ),
        Index(
            "uq_class_subject_primary_teacher",
            "school_class_id",
            "subject_id",
            sa_text("coalesce(subgroup_id, 0)"),
            unique=True,
            postgresql_where=sa_text(
                "is_primary = true AND is_active = true"
            ),
        ),
        Index(
            "ix_class_subject_teachers_staff_active",
            "staff_member_id",
            "is_active",
        ),
        Index(
            "ix_class_subject_teachers_school_active",
            "school_id",
            "is_active",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    school_id: Mapped[int] = mapped_column(
        ForeignKey(
            "schools.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    school_class_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    subject_id: Mapped[int] = mapped_column(
        ForeignKey(
            "subjects.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    subgroup_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    staff_member_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "school_staff_members.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    teacher_name_snapshot: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=sa_text("true"),
    )

    assigned_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    unassigned_at: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    school_class: Mapped[SchoolClass] = relationship(
        "SchoolClass",
        back_populates="subject_teachers",
        primaryjoin=(
            "SchoolClassSubjectTeacher.school_class_id "
            "== SchoolClass.id"
        ),
        foreign_keys="[SchoolClassSubjectTeacher.school_class_id]",
        lazy="raise",
    )

    subject: Mapped[Subject] = relationship(
        "Subject",
        back_populates="class_teacher_assignments",
        lazy="raise",
    )

    staff_member: Mapped[SchoolStaffMember | None] = relationship(
        "SchoolStaffMember",
        foreign_keys=[staff_member_id],
        lazy="raise",
    )

    def __repr__(self) -> str:
        return (
            f"<SchoolClassSubjectTeacher id={self.id} "
            f"school_id={self.school_id} "
            f"class_id={self.school_class_id} "
            f"subject_id={self.subject_id} "
            f"staff_member_id={self.staff_member_id}>"
        )


# =========================================================
# CURRICULUM / CLASS SUBJECTS / SUBJECT SUBGROUPS
# =========================================================

class SubjectMethodProfile(Base):
    """Global subject grouping for methodology; not a school's existing MO."""
    __tablename__ = 'subject_method_profiles'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(255))


class CurriculumSubjectRule(Base):
    __tablename__ = 'curriculum_subject_rules'
    __table_args__ = (
        UniqueConstraint('instruction_language', 'grade_level', 'education_track', 'subject_id',
                         name='uq_curriculum_subject_context'),
        CheckConstraint("instruction_language IN ('kz','ru','uz','tg','ug')", name='ck_curriculum_language'),
        CheckConstraint('grade_level BETWEEN 1 AND 12', name='ck_curriculum_grade'),
        CheckConstraint("education_track = '' OR (grade_level IN (10,11) AND education_track IN ('emn','ogn'))",
                        name='ck_curriculum_track'),
        CheckConstraint(
            "subject_role IN ('literacy', 'literary_reading', 'native_language', 'native_literature', 'general', "
            "'kz_language', 'kz_literature', 'kz_combined', 'ru_language', 'ru_literature', 'ru_combined', 'english', "
            "'mathematics', 'informatics', 'natural_science', 'physics', 'chemistry', 'biology', 'geography')",
            name="ck_curriculum_subject_role",
        ),

        CheckConstraint('split_threshold IS NULL OR split_threshold = 20', name='ck_curriculum_split'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    instruction_language: Mapped[str] = mapped_column(String(5))
    grade_level: Mapped[int] = mapped_column(Integer)
    education_track: Mapped[str] = mapped_column(String(10), default='', server_default='')
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id', ondelete='RESTRICT'))
    subject_role: Mapped[str] = mapped_column(String(30), default='general', server_default='general')
    method_profile_id: Mapped[int | None] = mapped_column(ForeignKey('subject_method_profiles.id', ondelete='RESTRICT'))
    split_threshold: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_text('true'))


class SchoolClassSubject(Base):
    __tablename__ = 'school_class_subjects'
    __table_args__ = (
        ForeignKeyConstraint(['school_class_id', 'school_id'], ['school_classes.id', 'school_classes.school_id'],
                             ondelete='RESTRICT'),
        UniqueConstraint('school_class_id', 'subject_id', name='uq_class_subject'),
        UniqueConstraint('id', 'school_id', name='uq_class_subject_school'),
        UniqueConstraint('id', 'school_class_id', 'subject_id', 'school_id', name='uq_class_subject_context'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    school_id: Mapped[int] = mapped_column(ForeignKey('schools.id', ondelete='RESTRICT'))
    school_class_id: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(ForeignKey('subjects.id', ondelete='RESTRICT'))
    rule_id: Mapped[int] = mapped_column(ForeignKey('curriculum_subject_rules.id', ondelete='RESTRICT'))
    split_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_text('false'))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_text('true'))


class SchoolSubjectSubgroup(Base):
    __tablename__ = 'school_subject_subgroups'
    __table_args__ = (
        ForeignKeyConstraint(['class_subject_id', 'school_class_id', 'subject_id', 'school_id'],
                             ['school_class_subjects.id', 'school_class_subjects.school_class_id',
                              'school_class_subjects.subject_id', 'school_class_subjects.school_id'],
                             ondelete='RESTRICT'),
        UniqueConstraint('class_subject_id', 'number', name='uq_subject_subgroup_number'),
        UniqueConstraint('id', 'class_subject_id', 'school_id', name='uq_subgroup_offer_school'),
        UniqueConstraint('id', 'school_class_id', 'subject_id', 'school_id', name='uq_subgroup_assignment_context'),
        CheckConstraint('number IN (1,2)', name='ck_subgroup_number'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    class_subject_id: Mapped[int] = mapped_column(Integer)
    school_id: Mapped[int] = mapped_column(Integer)
    school_class_id: Mapped[int] = mapped_column(Integer)
    subject_id: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_text('true'))


class SchoolSubjectSubgroupMember(Base):
    __tablename__ = 'school_subject_subgroup_members'
    __table_args__ = (
        ForeignKeyConstraint(['subgroup_id', 'class_subject_id', 'school_id'],
                             ['school_subject_subgroups.id', 'school_subject_subgroups.class_subject_id',
                              'school_subject_subgroups.school_id'], ondelete='RESTRICT'),
        ForeignKeyConstraint(['student_id', 'school_id'], ['school_students.id', 'school_students.school_id'],
                             ondelete='RESTRICT'),
        CheckConstraint('left_at IS NULL OR left_at >= joined_at', name='ck_subgroup_member_dates'),
        Index('uq_active_subject_subgroup_member', 'class_subject_id', 'student_id', unique=True,
              postgresql_where=sa_text('is_active = true')),
        Index('ix_subgroup_member_school', 'school_id', 'is_active'),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    class_subject_id: Mapped[int] = mapped_column(Integer)
    subgroup_id: Mapped[int] = mapped_column(Integer)
    school_id: Mapped[int] = mapped_column(Integer)
    student_id: Mapped[int] = mapped_column(Integer)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=sa_text('true'))
