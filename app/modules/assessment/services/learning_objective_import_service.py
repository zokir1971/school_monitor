"""Validated insert-only import. Caller owns commit/rollback."""

from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Any, Mapping, cast
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assessment.models_learning_objective_import import (
    LearningObjectiveImportDraft,
)
from app.modules.assessment.repositories.learning_objective_import_repo import (
    LearningObjectiveImportRepo,
)
from app.modules.assessment.helpers.learning_objective_reference_contract import (
    normalize_import_code,
    normalize_skill,
)

from app.modules.assessment.helpers.learning_objective_program_guard import (
    validate_binding,
)

from app.modules.assessment.helpers.learning_objective_rich_contract import validate_program_scope, validate_rich_row

TEXT_LIMIT = 20000


def text_value(
    value: object, label: str, *, required: bool = False, limit: int = TEXT_LIMIT
) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label}: ожидается текст.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"Заполните: {label}.")
    if len(value) > limit:
        raise ValueError(f"{label}: максимум {limit} символов.")
    return value


def validate_metadata(raw: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in ("document_key", "order_number", "appendix_number", "variant_key"):
        result[key] = text_value(
            raw.get(key, ""),
            key,
            required=True,
            limit=100 if key in ("order_number", "appendix_number") else 150,
        )
    for key in ("source_title_kz", "program_title_kz"):
        result[key] = text_value(raw.get(key, ""), key, required=True)
    for key in (
        "source_title_ru",
        "program_title_ru",
        "education_track",
        "instruction_language",
    ):
        result[key] = text_value(
            raw.get(key, ""),
            key,
            limit=(
                32
                if key == "instruction_language"
                else 100 if key == "education_track" else TEXT_LIMIT
            ),
        )
    for key in ("order_date", "edition_date"):
        try:
            result[key] = date.fromisoformat(raw.get(key, "")).isoformat()
        except (ValueError, TypeError):
            raise ValueError(f"{key}: укажите дату.") from None
    for key in ("subject_id", "grade_from", "grade_to"):
        try:
            result[key] = int(raw.get(key, ""))
        except (ValueError, TypeError):
            raise ValueError(f"{key}: ожидается целое число.") from None
    if (
        result["subject_id"] < 1
        or not 1 <= result["grade_from"] <= result["grade_to"] <= 12
    ):
        raise ValueError("Выберите предмет и диапазон классов 1–12.")
    validate_program_scope(result)
    return result


def validate_rows(
    rows: object, *, meta: Mapping[str, Any], payload: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
        raise ValueError("Нужно от 1 до 1000 целей.")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Строка {index}: неверный формат.")
        grade = row.get("grade_level")
        quarter = row.get("quarter")
        if (
            type(grade) is not int
            or not meta["grade_from"] <= grade <= meta["grade_to"]
        ):
            raise ValueError(f"Строка {index}: класс вне диапазона программы.")
        if type(quarter) is not int or not 1 <= quarter <= 4:
            raise ValueError(f"Строка {index}: выберите одну четверть 1–4.")
        entry: dict[str, Any] = {
            "grade_level": grade,
            "quarter": quarter,
            "code": normalize_import_code(row.get("code"), grade_level=grade),
        }
        if len(entry["code"]) > 100:
            raise ValueError(f"Строка {index}: код слишком длинный.")
        if entry["code"] in seen:
            raise ValueError(
                f"Повтор кода {entry['code']}: оставьте один проверенный вариант."
            )
        seen.add(entry["code"])
        for key in (
            "title_kz",
            "title_ru",
            "section_code",
            "subsection_code",
            "section_title_kz",
            "section_title_ru",
            "subsection_title_kz",
            "subsection_title_ru",
        ):
            entry[key] = text_value(
                row.get(key, ""),
                f"Строка {index}: {key}",
                required=key == "title_kz",
                limit=50 if key.endswith("_code") else TEXT_LIMIT,
            )
        entry["language_skill"] = normalize_skill(row.get("language_skill"))
        for language in ("kz", "ru"):
            key = "source_pages_" + language
            pages = row.get(key, [])
            allowed = payload.get("selected_pages_" + language, [])
            if not isinstance(pages, list) or any(
                type(p) is not int or p not in allowed for p in pages
            ):
                raise ValueError(
                    f"Строка {index}: страницы {language} вне выбранного PDF-диапазона."
                )
            entry[key] = sorted(set(pages))
        entry.update(validate_rich_row(row, label=f"Строка {index}"))
        entry["education_track"] = meta.get("education_track", "")
        result.append(entry)
    return result


async def confirm_import(
    db: AsyncSession, *, draft: LearningObjectiveImportDraft, rows: object
) -> dict[str, Any] | None:
    if draft.confirmed_at is not None:
        return cast(dict[str, Any] | None, draft.result)
    if draft.expires_at <= datetime.now(timezone.utc):
        raise ValueError("Предпросмотр истёк. Создайте новый импорт.")
    payload = cast(dict[str, Any], draft.payload)
    meta = validate_metadata(payload["metadata"])
    validated_rows = validate_rows(rows, meta=meta, payload=payload)
    repo = LearningObjectiveImportRepo
    subject_name = await repo.get_subject_name(db, meta["subject_id"])
    if subject_name is None:
        raise ValueError("Предмет не найден.")
    for language in ("kz", "ru"):
        if payload.get("file_key_" + language):
            validate_binding(
                payload.get("program_binding_" + language),
                subject_name=subject_name,
                meta=meta,
                pages=payload.get("selected_pages_" + language, []),
            )

    source_values: dict[str, Any] = {
        "document_key": meta["document_key"],
        "order_number": meta["order_number"],
        "order_date": date.fromisoformat(meta["order_date"]),
        "edition_date": date.fromisoformat(meta["edition_date"]),
        "title_kz": meta["source_title_kz"],
        "title_ru": meta["source_title_ru"] or None,
        "file_key_kz": payload["file_key_kz"],
        "file_key_ru": payload.get("file_key_ru"),
        "sha256_kz": payload["sha256_kz"],
        "sha256_ru": payload.get("sha256_ru"),
        "created_by_user_id": draft.owner_user_id,
    }
    source = await repo.get_source(db, meta["document_key"])
    if source is not None:
        for field in (
            "order_number",
            "order_date",
            "edition_date",
            "title_kz",
            "title_ru",
            "sha256_kz",
            "sha256_ru",
        ):
            if getattr(source, field) != source_values[field]:
                raise ValueError(
                    "Ключ источника уже используется для другого приказа, "
                    "редакции или PDF. Выберите другой document_key."
                )

    program_values: dict[str, Any] = {
        "subject_id": meta["subject_id"],
        "appendix_number": meta["appendix_number"],
        "variant_key": meta["variant_key"],
        "title_kz": meta["program_title_kz"],
        "title_ru": meta["program_title_ru"] or None,
        "grade_from": meta["grade_from"],
        "grade_to": meta["grade_to"],
        "education_track": meta["education_track"] or None,
        "instruction_language": meta["instruction_language"] or None,
    }
    program = None
    if source is not None:
        program = await repo.get_program(
            db,
            subject_id=meta["subject_id"],
            source_id=source.id,
            appendix_number=meta["appendix_number"],
            variant_key=meta["variant_key"],
        )
    if program is not None:
        if not program.is_active:
            raise ValueError("Программа отключена. Импорт в неё запрещён.")
        if any(getattr(program, key) != value for key, value in program_values.items()):
            raise ValueError(
                "Вариант программы уже существует с другими параметрами. "
                "Измените ключ варианта."
            )

    # Load the entire candidate set and quarter links before checking any row.
    existing_by_key = await repo.load_objectives(
        db,
        subject_id=meta["subject_id"],
        keys=[(row["grade_level"], row["code"]) for row in validated_rows],
        education_track=meta.get("education_track", ""),
    )
    quarters = await repo.load_quarters(
        db,
        [objective.id for objective in existing_by_key.values()],
    )
    new_fields: list[dict[str, Any]] = []
    skipped = 0
    for row in validated_rows:
        fields: dict[str, Any] = {
            key: (
                value
                if key
                in (
                    "title_kz",
                    "education_track",
                    "has_formula_kz", "has_formula_ru",
                    "formula_reviewed_kz", "formula_reviewed_ru",
                    "title_segments_kz", "title_segments_ru",
                    "source_pages_kz",
                    "source_pages_ru",
                    "grade_level",
                    "quarter",
                    "code",
                )
                else value or None
            )
            for key, value in row.items()
        }
        existing = existing_by_key.get((row["grade_level"], row["code"]))
        if existing is None:
            new_fields.append(fields)
            continue
        if not existing.is_active:
            raise ValueError(
                f"Цель {row['code']} отключена. Импорт не активирует её автоматически."
            )
        if (
            program is None
            or existing.program_id != program.id
            or any(getattr(existing, key) != value for key, value in fields.items())
        ):
            raise ValueError(
                f"Код {row['code']} уже существует с другими данными или в другой "
                "программе. Существующая цель не изменена."
            )
        if (existing.id, row["quarter"]) not in quarters:
            raise ValueError(
                "Нарушена связь с четвертью. Выполните проверку первого этапа."
            )
        skipped += 1

    # All rows passed validation. No query or flush occurs inside the row loop.
    if source is None:
        source = await repo.create_source(db, source_values)
    if program is None:
        program = await repo.create_program(
            db,
            {**program_values, "source_id": source.id},
        )
    objective_values = [
        {
            **fields,
            "subject_id": meta["subject_id"],
            "program_id": program.id,
            "is_active": True,
        }
        for fields in new_fields
    ]
    result: dict[str, Any] = {
        "created": len(objective_values),
        "skipped": skipped,
        "source_id": source.id,
        "program_id": program.id,
    }
    await repo.save_confirmed_batch(
        db,
        draft=draft,
        objective_values=objective_values,
        payload={**payload, "rows": validated_rows},
        result=result,
        confirmed_at=datetime.now(timezone.utc),
    )
    return result
