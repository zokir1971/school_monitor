# app/modules/reports/models_template_reports.py

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func, Boolean,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class LessonObservationReport(Base):
    """
    Сабақты бақылау парағы / Лист наблюдения урока.

    Хранит данные, введенные исполнителем в шаблон отчета.
    Сам документ, статус, report_code, отправка и файл хранятся
    в TaskExecutionDocument.
    """

    __tablename__ = "lesson_observation_reports"

    __table_args__ = (
        UniqueConstraint(
            "task_execution_document_id",
            name="uq_lesson_observation_task_document",
        ),
        Index("ix_lesson_observation_month_item", "month_item_id"),
        Index("ix_lesson_observation_document", "task_execution_document_id"),
        Index("ix_lesson_observation_teacher", "staff_member_id"),
        Index("ix_lesson_observation_observer", "observer_user_id"),
        Index("ix_lesson_observation_lesson_datetime", "lesson_datetime"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # =========================
    # Базовые связи
    # =========================
    month_item_id: Mapped[int] = mapped_column(
        ForeignKey("school_month_plan_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_execution_document_id: Mapped[int] = mapped_column(
        ForeignKey("task_execution_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Учитель, чей урок наблюдали
    staff_member_id: Mapped[int | None] = mapped_column(
        ForeignKey("school_staff_members.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Наблюдатель урока = исполнитель задачи
    observer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # =========================
    # Snapshot учителя
    # =========================
    teacher_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teacher_position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teacher_category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teacher_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # =========================
    # Snapshot наблюдателя
    # =========================
    observer_full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observer_position: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # =========================
    # Данные урока
    # =========================
    school_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    class_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    lesson_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    theme: Mapped[str | None] = mapped_column(Text, nullable=True)

    learning_objectives: Mapped[str | None] = mapped_column(Text, nullable=True)

    lesson_objectives_1: Mapped[str | None] = mapped_column(Text, nullable=True)
    lesson_objectives_2: Mapped[str | None] = mapped_column(Text, nullable=True)
    lesson_objectives_3: Mapped[str | None] = mapped_column(Text, nullable=True)

    lesson_plan_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # =========================
    # Оценивание
    # =========================
    criteria_scores: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    col_sum_0: Mapped[int | None] = mapped_column(Integer, nullable=True)
    col_sum_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    col_sum_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    col_sum_3: Mapped[int | None] = mapped_column(Integer, nullable=True)

    total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # =========================
    # Итоги / рекомендации
    # =========================
    suggestion_control: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # =========================
    # Сгенерированные файлы
    # =========================
    pdf_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pdf_signed_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qr_file: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # =========================
    # Даты
    # =========================
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # =========================
    # Relationships
    # =========================
    month_item = relationship("SchoolMonthPlanItem", lazy="selectin")

    task_execution_document = relationship("TaskExecutionDocument", lazy="selectin")

    staff_member = relationship("SchoolStaffMember", foreign_keys=[staff_member_id], lazy="selectin")

    observer_user = relationship("User", foreign_keys=[observer_user_id], lazy="selectin")


class UserReportTemplate(Base):
    """
    Личный шаблон отчета исполнителя.

    Это НЕ документ конкретной задачи.
    Это библиотека шаблонов пользователя, которую он может использовать повторно.

    Пример:
    - исполнитель создал свой шаблон для Сабақты бақылау парағы;
    - потом применяет его в разных задачах;
    - при применении в задачу копия текста сохраняется в TaskExecutionDocument.
    """

    __tablename__ = "user_report_templates"

    __table_args__ = (
        UniqueConstraint(
            "owner_user_id",
            "report_code",
            "title",
            name="uq_user_report_template_owner_code_title",
        ),
        Index("ix_user_report_templates_owner", "owner_user_id"),
        Index("ix_user_report_templates_report_type", "report_type_id"),
        Index("ix_user_report_templates_report_code", "report_code"),
        Index("ix_user_report_templates_owner_code_active", "owner_user_id", "report_code", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # связь с report_types, если тип есть в БД
    report_type_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # стабильный код из ReportType enum / report_types.code
    report_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # snapshot названия типа отчета
    report_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    schema_json: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    owner_user = relationship("User", lazy="selectin")

    report_type = relationship("ReportTypeModel", lazy="selectin")


class CheckingNotebooksReport(Base):
    """
    Проверка тетрадей.

    Хранит данные, введенные исполнителем в шаблон отчета.
    Структура шаблона хранится в UserReportTemplate.schema_json.
    Здесь сохраняется только результат заполнения.
    """

    __tablename__ = "checking_notebooks_reports"

    __table_args__ = (
        UniqueConstraint(
            "task_execution_document_id",
            name="uq_checking_notebooks_task_document",
        ),
        Index("ix_checking_notebooks_month_item", "month_item_id"),
        Index("ix_checking_notebooks_document", "task_execution_document_id"),
        Index("ix_checking_notebooks_template", "user_template_id"),
        Index("ix_checking_notebooks_observer", "observer_user_id"),
        Index("ix_checking_notebooks_check_date", "check_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # =========================
    # Базовые связи
    # =========================
    month_item_id: Mapped[int] = mapped_column(
        ForeignKey("school_month_plan_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_execution_document_id: Mapped[int] = mapped_column(
        ForeignKey("task_execution_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_template_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_report_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    observer_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    selected_report_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # =========================
    # Snapshot общей информации
    # =========================
    school_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    checker_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    checker_post: Mapped[str | None] = mapped_column(String(255), nullable=True)

    teacher_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    class_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    check_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # =========================
    # Данные таблицы
    # =========================
    rows_json: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # =========================
    # Итоги
    # =========================
    total_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    level: Mapped[str | None] = mapped_column(String(100), nullable=True)

    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[str | None] = mapped_column(Text, nullable=True)

    # =========================
    # Сгенерированные файлы
    # =========================
    pdf_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pdf_signed_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qr_file: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # =========================
    # Даты
    # =========================
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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

    # =========================
    # Relationships
    # =========================
    month_item = relationship("SchoolMonthPlanItem", lazy="selectin")

    task_execution_document = relationship("TaskExecutionDocument", lazy="selectin")

    user_template = relationship("UserReportTemplate", lazy="selectin")

    observer_user = relationship("User", foreign_keys=[observer_user_id], lazy="selectin")
