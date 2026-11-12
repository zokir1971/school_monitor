# app/scripts/seed_assessment_reference_data.py

from __future__ import annotations

import asyncio

from sqlalchemy import select

import app.db.models  # noqa: F401

from app.db.session import async_session_maker
from app.modules.assessment.models import LearningObjective
from app.modules.education.models import Subject


SUBJECTS = (
    {
        "code": "informatics",
        "name_kz": "Информатика",
        "name_ru": "Информатика",
        "sort_order": 10,
    },
    {
        "code": "mathematics",
        "name_kz": "Математика",
        "name_ru": "Математика",
        "sort_order": 20,
    },
    {
        "code": "physics",
        "name_kz": "Физика",
        "name_ru": "Физика",
        "sort_order": 30,
    },
    {
        "code": "chemistry",
        "name_kz": "Химия",
        "name_ru": "Химия",
        "sort_order": 40,
    },
    {
        "code": "biology",
        "name_kz": "Биология",
        "name_ru": "Биология",
        "sort_order": 50,
    },
    {
        "code": "geography",
        "name_kz": "География",
        "name_ru": "География",
        "sort_order": 60,
    },
    {
        "code": "kazakh_language",
        "name_kz": "Қазақ тілі",
        "name_ru": "Казахский язык",
        "sort_order": 70,
    },
    {
        "code": "kazakh_literature",
        "name_kz": "Қазақ әдебиеті",
        "name_ru": "Казахская литература",
        "sort_order": 80,
    },
    {
        "code": "russian_language",
        "name_kz": "Орыс тілі",
        "name_ru": "Русский язык",
        "sort_order": 90,
    },
    {
        "code": "russian_literature",
        "name_kz": "Орыс әдебиеті",
        "name_ru": "Русская литература",
        "sort_order": 100,
    },
    {
        "code": "english_language",
        "name_kz": "Ағылшын тілі",
        "name_ru": "Английский язык",
        "sort_order": 110,
    },
    {
        "code": "history_kazakhstan",
        "name_kz": "Қазақстан тарихы",
        "name_ru": "История Казахстана",
        "sort_order": 120,
    },
    {
        "code": "world_history",
        "name_kz": "Дүниежүзі тарихы",
        "name_ru": "Всемирная история",
        "sort_order": 130,
    },
)


# Только DEV-данные.
# Эти коды намеренно НЕ похожи на официальные учебные цели.
TEST_OBJECTIVES = (
    {
        "subject_code": "informatics",
        "grade_level": 9,
        "code": "TEST-INF-9-001",
        "title_kz": "Ақпаратты өңдеу бойынша тестілік оқу мақсаты",
        "title_ru": "Тестовая учебная цель по обработке информации",
    },
    {
        "subject_code": "informatics",
        "grade_level": 9,
        "code": "TEST-INF-9-002",
        "title_kz": "Алгоритмдерді қолдану бойынша тестілік оқу мақсаты",
        "title_ru": "Тестовая учебная цель по применению алгоритмов",
    },
    {
        "subject_code": "informatics",
        "grade_level": 9,
        "code": "TEST-INF-9-003",
        "title_kz": "Деректермен жұмыс бойынша тестілік оқу мақсаты",
        "title_ru": "Тестовая учебная цель по работе с данными",
    },
    {
        "subject_code": "mathematics",
        "grade_level": 9,
        "code": "TEST-MATH-9-001",
        "title_kz": "Есептерді шығару бойынша тестілік оқу мақсаты",
        "title_ru": "Тестовая учебная цель по решению задач",
    },
)


async def seed_subjects(db) -> dict[str, Subject]:
    result = await db.execute(
        select(Subject)
    )

    existing = {
        subject.code: subject
        for subject in result.scalars().all()
    }

    for item in SUBJECTS:
        subject = existing.get(item["code"])

        if subject is None:
            subject = Subject(
                code=item["code"],
                name_kz=item["name_kz"],
                name_ru=item["name_ru"],
                sort_order=item["sort_order"],
                is_active=True,
            )

            db.add(subject)
            existing[item["code"]] = subject

        else:
            subject.name_kz = item["name_kz"]
            subject.name_ru = item["name_ru"]
            subject.sort_order = item["sort_order"]
            subject.is_active = True

    await db.flush()

    return existing


async def seed_test_objectives(
    db,
    *,
    subjects: dict[str, Subject],
) -> None:
    result = await db.execute(
        select(LearningObjective)
    )

    existing = {
        (
            objective.subject_id,
            objective.grade_level,
            objective.code,
        )
        for objective in result.scalars().all()
    }

    for item in TEST_OBJECTIVES:
        subject = subjects[item["subject_code"]]

        key = (
            subject.id,
            item["grade_level"],
            item["code"],
        )

        if key in existing:
            continue

        db.add(
            LearningObjective(
                subject_id=subject.id,
                grade_level=item["grade_level"],
                code=item["code"],
                title_kz=item["title_kz"],
                title_ru=item["title_ru"],
                is_active=True,
            )
        )


async def main() -> None:
    async with async_session_maker() as db:
        try:
            subjects = await seed_subjects(db)

            await seed_test_objectives(
                db,
                subjects=subjects,
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    print(
        "Assessment reference data seeded successfully."
    )


if __name__ == "__main__":
    asyncio.run(main())
