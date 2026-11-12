"""Validated insert-only import. Caller owns commit/rollback."""

from __future__ import annotations
from datetime import date, datetime, timezone
from typing import Any, Mapping, cast
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.assessment.models_learning_objective_import import (
    LearningObjectiveImportDraft,
)
from app.modules.assessment.repositories.learning_objective_table_import_repo import (
    LearningObjectiveTableImportRepo,
)
from app.modules.assessment.helpers.learning_objective_reference_contract import (
    normalize_import_code,
    normalize_quarters,
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
    grouped: dict[str, dict[str, Any]] = {}
    originals = {str(item.get("import_row_id", index)): item for index, item in enumerate(payload["rows"])}
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Строка {index}: неверный формат.")
        grade = row.get("grade_level")
        quarters = normalize_quarters(row.get("quarters"))
        quarter = min(quarters)
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
            "quarters": list(quarters),
            "code": normalize_import_code(row.get("code"), grade_level=grade),
        }
        if len(entry["code"]) > 100:
            raise ValueError(f"Строка {index}: код слишком длинный.")
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
                required=False,
                limit=50 if key.endswith("_code") else TEXT_LIMIT,
            )
        skill = row.get("language_skill") or None
        if skill not in (
            None,
            "listening",
            "speaking",
            "reading",
            "writing",
            "listening_speaking",
            'language_skills',
            "language_norms",
        ):
            raise ValueError(f"Строка {index}: неизвестный навык.")
        entry["language_skill"] = skill
        for language in ("kz", "ru"):
            entry["source_pages_" + language] = []
            # Provenance comes only from the server-side draft, never from editable JSON.
            original = originals.get(str(row.get("import_row_id", "")))
            if original is not None and original["code"] != entry["code"]:
                raise ValueError("Код исходной формулировки менять нельзя; добавьте новую строку.")
            entry["source_cells_" + language] = list(original.get("source_cells_" + language, [])) if original else []
        entry.update(validate_rich_row(row, label=f"Строка {index}", require_kz=False))
        entry["education_track"] = meta.get("education_track", "")
        if not entry["title_kz"] and not entry["title_ru"]:
            raise ValueError(f"Строка {index}: заполните текст хотя бы на одном языке.")
        forms = []
        for language in ("kz", "ru"):
            if not entry["title_" + language]:
                continue
            forms.append({
                "language": language, "title": entry["title_" + language],
                "segments": entry["title_segments_" + language], "quarters": list(quarters),
                "source_cells": list(entry["source_cells_" + language]),
                "source_text": original.get("title_" + language, "") if original else "",
                "metadata_json": {"source_quarters": list(
                    original.get("quarters", quarters)) if original else list(quarters),
                                  **{key: entry.get(key) for key in (
                                      "language_skill", "section_code", "subsection_code",
                                      "section_title_" + language, "subsection_title_" + language,
                                      "has_formula_" + language, "formula_reviewed_" + language)}},
            })
        code = entry["code"]
        if code not in grouped:
            entry["formulations"] = forms
            grouped[code] = entry
        else:
            target = grouped[code]
            target["quarters"] = sorted(set(target["quarters"] + entry["quarters"]))
            target["quarter"] = min(target["quarters"])
            target["formulations"].extend(forms)
            for language in ("kz", "ru"):
                target["source_cells_" + language].extend(entry["source_cells_" + language])
                if not target["title_" + language] and entry["title_" + language]:
                    for key in ("title", "title_segments", "has_formula", "formula_reviewed"):
                        target[key + "_" + language] = entry[key + "_" + language]
        result = list(grouped.values())
    # Keep the legacy non-null KZ column usable for RU-only source variants.
    for entry in result:
        if not entry["title_kz"]:
            entry["title_kz"] = entry["title_ru"]
    return result


async def confirm_table_import(
    db: AsyncSession, *, draft: LearningObjectiveImportDraft, rows: object
) -> dict[str, Any] | None:
    if draft.confirmed_at is not None:
        return cast(dict[str, Any] | None, draft.result)
    if draft.expires_at <= datetime.now(timezone.utc):
        raise ValueError("Предпросмотр истёк. Создайте новый импорт.")
    payload = cast(dict[str, Any], draft.payload)
    meta = validate_metadata(payload["metadata"])
    validated_rows = validate_rows(rows, meta=meta, payload=payload)
    repo = LearningObjectiveTableImportRepo
    subject_name = await repo.get_subject_name(db, meta["subject_id"])
    if subject_name is None:
        raise ValueError("Предмет не найден.")
    binding = payload.get("table_binding", {})
    if (
        payload.get("import_kind") != "table_v1"
        or binding.get("subject_id") != meta["subject_id"]
        or binding.get("subject_name") != subject_name
        or not binding.get("confirmed")
    ):
        raise ValueError(
            "Предмет или подтверждённая привязка к источнику изменились. Создайте новый предпросмотр."
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
    if program is None:
        repeat = await repo.find_repeat_program(db, meta=meta)
        if repeat is not None:
            program, source = repeat
            if source.title_kz != source_values["title_kz"] or source.title_ru != source_values["title_ru"]:
                raise ValueError("Названия источника отличаются от сохранённого приказа. Проверьте реквизиты.")
    if program is not None:
        if not program.is_active:
            raise ValueError("Программа отключена. Импорт в неё запрещён.")
        if any(getattr(program, key) != value for key, value in program_values.items()):
            raise ValueError(
                "Вариант программы уже существует с другими параметрами. "
                "Измените ключ варианта."
            )

    # Load the entire candidate set and quarter links before checking any row.
    # A new program has no saved objectives. Never adopt another program's rows.
    existing_by_key = {}
    if program is not None:
        existing_by_key = await repo.load_objectives(
            db,
            subject_id=meta["subject_id"],
            program_id=program.id,
            keys=[(row["grade_level"], row["code"]) for row in validated_rows],
            education_track=meta.get("education_track", ""),
        )
    quarters = await repo.load_quarters(
        db,
        [objective.id for objective in existing_by_key.values()],
    )
    new_fields: list[dict[str, Any]] = []
    skipped = 0
    additional_quarters = []
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
                    "source_cells_kz",
                    "source_cells_ru",
                    "grade_level",
                    "quarter",
                    "code",
                )
                else value or None
            )
            for key, value in row.items()
            if key not in ("quarters", "formulations")
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

        ):
            raise ValueError(
                f"Код {row['code']} уже существует с другими данными или в другой "
                "программе. Существующая цель не изменена."
            )
        additional_quarters.extend(
            {"learning_objective_id": existing.id, "quarter": q}
            for q in row["quarters"]
            if (existing.id, q) not in quarters
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
        "quarters_added": len(additional_quarters),
        "source_id": source.id,
        "program_id": program.id,
    }
    await repo.save_table_batch(
        db,
        draft=draft,
        objective_values=objective_values,
        additional_quarters=additional_quarters,
        payload={
            **payload,
            "rows": validated_rows,
            "quarter_map": {r["code"]: r["quarters"] for r in validated_rows},
        },
        result=result,
        formulations={row["code"]: row["formulations"] for row in validated_rows},
        existing_objectives=existing_by_key,
    )
    return result
