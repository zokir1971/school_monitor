from __future__ import annotations

import asyncio
import app.db.models  # noqa: F401

from app.db.session import async_session_maker

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import delete, event, select

from app.db.session import get_db
from app.modules.assessment.enums import (
    AssessmentLanguage,
    AssessmentQuestionDifficulty,
    AssessmentQuestionType,
    QuestionBankItemOrigin,
    QuestionBankItemStatus,
)
from app.modules.assessment.models import (
    LearningObjective,
    QuestionBankItem,
    QuestionBankItemObjective,
)
from app.modules.assessment.schemas.teacher_question_bank_dto import (
    TeacherQuestionBankCreateDraftDTO,
)
from app.modules.assessment.services.teacher_question_bank_service import (
    TeacherQuestionBankService,
)
from app.modules.education.models import (
    SchoolClass,
    SchoolClassSubjectTeacher,
)
from app.modules.users.enums import UserRole
from app.modules.users.models import User


# =========================================================
# TEST CONSTANTS
# =========================================================

TEST_TITLE = "CASE 68_1 — Teacher Question Bank Draft"

TEST_TEXT = (
    "Алгоритмнің бірінші қадамын таңдаңыз."
)

TEST_INSTRUCTION = (
    "Бір дұрыс жауапты таңдаңыз."
)

TEST_EXPLANATION = (
    "Алгоритм бастапқы деректерді "
    "қабылдаудан басталады."
)

TEST_AUTHOR_COMMENT = (
    "CASE 68_1 integration test"
)


# =========================================================
# HELPERS
# =========================================================

async def find_teacher_context(
    db,
) -> tuple[
    int,
    int,
    int,
    int,
    int,
    list[int],
]:
    """
    Находит реального активного учителя,
    его teaching scope и минимум две активные
    LearningObjective одной четверти.

    Возвращает:

        user_id
        staff_member_id
        subject_id
        grade_level
        quarter
        objective_ids
    """

    stmt = (
        select(
            User.id.label("user_id"),
            User.staff_member_id.label(
                "staff_member_id"
            ),
            SchoolClassSubjectTeacher.subject_id.label(
                "subject_id"
            ),
            SchoolClass.grade_level.label(
                "grade_level"
            ),
            LearningObjective.quarter.label(
                "quarter"
            ),
            LearningObjective.id.label(
                "learning_objective_id"
            ),
        )
        .select_from(User)
        .join(
            SchoolClassSubjectTeacher,
            SchoolClassSubjectTeacher.staff_member_id
            == User.staff_member_id,
        )
        .join(
            SchoolClass,
            SchoolClass.id
            == SchoolClassSubjectTeacher.school_class_id,
        )
        .join(
            LearningObjective,
            (
                LearningObjective.subject_id
                == SchoolClassSubjectTeacher.subject_id
            )
            & (
                LearningObjective.grade_level
                == SchoolClass.grade_level
            ),
        )
        .where(
            User.role == UserRole.TEACHER,
            User.is_active.is_(True),
            User.staff_member_id.is_not(None),

            SchoolClassSubjectTeacher.is_active.is_(True),
            SchoolClass.is_active.is_(True),

            LearningObjective.is_active.is_(True),
        )
        .order_by(
            User.id.asc(),
            SchoolClassSubjectTeacher.subject_id.asc(),
            SchoolClass.grade_level.asc(),
            LearningObjective.quarter.asc(),
            LearningObjective.id.asc(),
        )
    )

    result = await db.execute(stmt)

    rows = result.all()

    grouped: dict[
        tuple[int, int, int, int, int],
        list[int],
    ] = defaultdict(list)

    for row in rows:
        key = (
            row.user_id,
            row.staff_member_id,
            row.subject_id,
            row.grade_level,
            row.quarter,
        )

        objective_id = (
            row.learning_objective_id
        )

        if objective_id not in grouped[key]:
            grouped[key].append(
                objective_id
            )

    for key, objective_ids in grouped.items():
        if len(objective_ids) < 2:
            continue

        (
            user_id,
            staff_member_id,
            subject_id,
            grade_level,
            quarter,
        ) = key

        return (
            user_id,
            staff_member_id,
            subject_id,
            grade_level,
            quarter,
            objective_ids[:2],
        )

    raise RuntimeError(
        "CASE 68_1 requires an active teacher "
        "with at least two active LearningObjective "
        "for the same subject, grade and quarter."
    )


async def cleanup_old_test_rows(
    db,
) -> None:
    """
    Удаляет остатки предыдущего запуска CASE 68_1.

    QuestionBankItemObjective удаляются через
    ON DELETE CASCADE.
    """

    stmt = (
        delete(QuestionBankItem)
        .where(
            QuestionBankItem.title
            == TEST_TITLE
        )
    )

    await db.execute(stmt)
    await db.commit()


# =========================================================
# TEST
# =========================================================

async def run() -> None:
    db_generator = get_db()

    db = await anext(
        db_generator
    )

    created_item_id: int | None = None

    try:
        print()
        print("=" * 70)
        print(
            "CASE 68_1 — "
            "TEACHER QUESTION BANK CREATE DRAFT"
        )
        print("=" * 70)

        # -------------------------------------------------
        # CLEANUP FROM PREVIOUS RUN
        # -------------------------------------------------

        await cleanup_old_test_rows(
            db
        )

        # -------------------------------------------------
        # REAL TEST CONTEXT
        # -------------------------------------------------

        (
            user_id,
            staff_member_id,
            subject_id,
            grade_level,
            quarter,
            objective_ids,
        ) = await find_teacher_context(
            db
        )

        print(
            "TEACHER USER ID:",
            user_id,
        )

        print(
            "STAFF MEMBER ID:",
            staff_member_id,
        )

        print(
            "SUBJECT ID:",
            subject_id,
        )

        print(
            "GRADE LEVEL:",
            grade_level,
        )

        print(
            "QUARTER:",
            quarter,
        )

        print(
            "OBJECTIVE IDS:",
            objective_ids,
        )

        assert len(objective_ids) == 2

        print(
            "OK: teacher context resolved"
        )

        # -------------------------------------------------
        # CREATE COMMAND
        # -------------------------------------------------

        data = TeacherQuestionBankCreateDraftDTO(
            subject_id=subject_id,
            grade_level=grade_level,
            quarter=quarter,

            objective_ids=[
                objective_ids[0],
                objective_ids[1],
            ],

            question_type=(
                AssessmentQuestionType.SINGLE_CHOICE
            ),

            difficulty=(
                AssessmentQuestionDifficulty.BASIC
            ),

            language=AssessmentLanguage.KAZAKH,

            title=TEST_TITLE,

            text=TEST_TEXT,

            instruction=TEST_INSTRUCTION,

            content={
                "options": [
                    {
                        "value": "A",
                        "text": "Деректерді енгізу",
                    },
                    {
                        "value": "B",
                        "text": "Нәтижені шығару",
                    },
                    {
                        "value": "C",
                        "text": "Алгоритмді аяқтау",
                    },
                ],
            },

            answer_key={
                "value": "A",
            },

            grading_settings={},

            max_score=Decimal(
                "1.00"
            ),

            explanation=(
                TEST_EXPLANATION
            ),

            author_comment=(
                TEST_AUTHOR_COMMENT
            ),
        )

        # -------------------------------------------------
        # SQL SELECT COUNTER
        #
        # Считаем только SELECT внутри create_draft().
        #
        # Ожидается:
        #
        # 1. has_teaching_scope()
        # 2. list_objectives_for_validation()
        #
        # Количество выбранных objectives не должно
        # создавать дополнительные SELECT.
        # -------------------------------------------------

        select_count = 0

        bind = db.get_bind()

        def before_cursor_execute(
            conn,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ) -> None:
            nonlocal select_count

            normalized = (
                statement
                .lstrip()
                .upper()
            )

            if normalized.startswith(
                "SELECT"
            ):
                select_count += 1

        event.listen(
            bind,
            "before_cursor_execute",
            before_cursor_execute,
        )

        try:
            created = (
                await TeacherQuestionBankService.create_draft(
                    db,
                    user_id=user_id,
                    staff_member_id=staff_member_id,
                    data=data,
                )
            )

        finally:
            event.remove(
                bind,
                "before_cursor_execute",
                before_cursor_execute,
            )

        created_item_id = (
            created.item_id
        )

        print(
            "QUESTION CREATED:",
            created.item_id,
        )

        print(
            "RETURNED STATUS:",
            created.status.value,
        )

        print(
            "SERVICE SELECT COUNT:",
            select_count,
        )

        # -------------------------------------------------
        # SERVICE RESULT
        # -------------------------------------------------

        assert created.item_id > 0

        assert (
            created.status
            == QuestionBankItemStatus.DRAFT
        )

        print(
            "OK: service returned DRAFT"
        )

        # -------------------------------------------------
        # N+1 CHECK
        # -------------------------------------------------

        assert select_count == 2, (
            "Expected exactly 2 SELECT queries "
            "inside create_draft(), "
            f"got {select_count}."
        )

        print(
            "OK: exactly 2 SELECT queries "
            "inside create_draft()"
        )

        print(
            "OK: no objective N+1 SELECT"
        )

        # -------------------------------------------------
        # RELOAD QUESTION FROM DATABASE
        # -------------------------------------------------

        item_stmt = (
            select(
                QuestionBankItem
            )
            .where(
                QuestionBankItem.id
                == created.item_id
            )
        )

        item_result = await db.execute(
            item_stmt
        )

        item = (
            item_result.scalar_one()
        )

        print(
            "DB STATUS:",
            item.status.value,
        )

        print(
            "DB ORIGIN:",
            item.origin.value,
        )

        print(
            "DB CREATED BY:",
            item.created_by_user_id,
        )

        # -------------------------------------------------
        # QUESTION ASSERTIONS
        # -------------------------------------------------

        assert (
            item.status
            == QuestionBankItemStatus.DRAFT
        )

        assert (
            item.origin
            == QuestionBankItemOrigin.MANUAL
        )

        assert (
            item.created_by_user_id
            == user_id
        )

        assert (
            item.subject_id
            == subject_id
        )

        assert (
            item.grade_level
            == grade_level
        )

        assert (
            item.question_type
            == AssessmentQuestionType.SINGLE_CHOICE
        )

        assert (
            item.difficulty
            == AssessmentQuestionDifficulty.BASIC
        )

        assert (
            item.language
            == AssessmentLanguage.KAZAKH
        )

        assert (
            item.title
            == TEST_TITLE
        )

        assert (
            item.text
            == TEST_TEXT
        )

        assert (
            item.instruction
            == TEST_INSTRUCTION
        )

        assert (
            item.max_score
            == Decimal("1.00")
        )

        assert (
            item.content
            == data.content
        )

        assert (
            item.answer_key
            == data.answer_key
        )

        assert (
            item.grading_settings
            == data.grading_settings
        )

        assert (
            item.explanation
            == TEST_EXPLANATION
        )

        assert (
            item.author_comment
            == TEST_AUTHOR_COMMENT
        )

        print(
            "OK: QuestionBankItem persisted"
        )

        print(
            "OK: status is DRAFT"
        )

        print(
            "OK: origin is MANUAL"
        )

        print(
            "OK: author persisted"
        )

        print(
            "OK: question contract persisted"
        )

        # -------------------------------------------------
        # RELOAD OBJECTIVE LINKS
        #
        # Один SELECT для всех связей.
        # -------------------------------------------------

        links_stmt = (
            select(
                QuestionBankItemObjective
            )
            .where(
                QuestionBankItemObjective
                .question_bank_item_id
                == created.item_id
            )
            .order_by(
                QuestionBankItemObjective
                .order_no
                .asc()
            )
        )

        links_result = await db.execute(
            links_stmt
        )

        links = list(
            links_result.scalars().all()
        )

        print(
            "OBJECTIVE LINKS:",
            [
                (
                    link.learning_objective_id,
                    link.order_no,
                )
                for link in links
            ],
        )

        assert len(links) == 2

        assert (
            links[0].learning_objective_id
            == objective_ids[0]
        )

        assert (
            links[0].order_no
            == 1
        )

        assert (
            links[1].learning_objective_id
            == objective_ids[1]
        )

        assert (
            links[1].order_no
            == 2
        )

        print(
            "OK: two objectives persisted"
        )

        print(
            "OK: objective order preserved"
        )

        # -------------------------------------------------
        # FINAL
        # -------------------------------------------------

        print()
        print("=" * 70)
        print(
            "CASE 68_1 PASSED"
        )
        print(
            "Teacher Question Bank draft creation "
            "works correctly."
        )
        print("=" * 70)

    finally:
        # -------------------------------------------------
        # CLEANUP
        # -------------------------------------------------

        try:
            if created_item_id is not None:
                await db.execute(
                    delete(
                        QuestionBankItem
                    ).where(
                        QuestionBankItem.id
                        == created_item_id
                    )
                )

                await db.commit()

                print(
                    "CLEANUP: test question deleted"
                )

        except Exception:
            await db.rollback()
            raise

        finally:
            await db_generator.aclose()


if __name__ == "__main__":
    asyncio.run(
        run()
    )
