"""School method-association settings with consistent legacy matching."""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.schools.method_association_dto import (
    MethodAssociationSettingsItemDTO,
    MethodAssociationSettingsPageDTO,
)
from app.modules.schools.method_assoc import (
    METHOD_ASSOCIATION_CODES,
    METHOD_ASSOCIATION_OPTIONS,
)
from app.modules.schools.method_association_repo import SchoolMethodAssociationRepository as Repo


class MethodAssociationSettingsConflict(ValueError):
    """A stale form or ambiguous saved association requires a fresh review."""


class MethodAssociationDataConflict(MethodAssociationSettingsConflict):
    """Existing rows cannot be reconciled without an explicit data decision."""


class SchoolMethodAssociationService:
    @staticmethod
    def _name_key(value: str) -> str:
        return " ".join(value.split()).casefold()

    @classmethod
    def _matching_items(cls, items):
        """Valid codes are authoritative; only empty-code rows use name fallback."""
        by_name = {cls._name_key(option.name): option.code for option in METHOD_ASSOCIATION_OPTIONS}
        matches = {option.code: [] for option in METHOD_ASSOCIATION_OPTIONS}
        for item in items:
            code = item.code
            if code in METHOD_ASSOCIATION_CODES:
                matches[code].append(item)
            elif not (code or "").strip():
                legacy_code = by_name.get(cls._name_key(item.name))
                if legacy_code is not None:
                    matches[legacy_code].append(item)
        return matches

    @staticmethod
    def _settings_version(school_id, items) -> str:
        data = [school_id, sorted(
            [(item.id, item.code, item.name, bool(item.is_active)) for item in items],
            key=lambda row: row[0],
        )]
        return hashlib.sha256(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

    @classmethod
    async def get_settings_page_data(cls, db: AsyncSession, *, school_id: int) -> MethodAssociationSettingsPageDTO:
        items = await Repo.get_all_by_school(db, school_id=school_id)
        matches = cls._matching_items(items)
        return MethodAssociationSettingsPageDTO(
            school_id=school_id,
            options=[MethodAssociationSettingsItemDTO(
                code=option.code, name=option.name,
                selected=any(item.is_active for item in matches[option.code]),
            ) for option in METHOD_ASSOCIATION_OPTIONS],
            settings_version=cls._settings_version(school_id, items),
        )

    @classmethod
    async def update_settings(
        cls, db: AsyncSession, *, school_id: int,
        selected_codes: list[str], expected_version: str,
    ) -> None:
        normalized_codes = cls._normalize_selected_codes(selected_codes)
        cls._validate_selected_codes(normalized_codes)
        if not isinstance(expected_version, str) or len(expected_version) != 64:
            raise MethodAssociationSettingsConflict("Missing settings version")

        # Lock the parent even for a school's first save (no child rows yet).
        # A following read reloads data changed by the preceding writer.
        if not await Repo.lock_school(db, school_id=school_id):
            raise ValueError("School not found")
        items = await Repo.get_all_by_school(db, school_id=school_id, refresh=True)
        if expected_version != cls._settings_version(school_id, items):
            raise MethodAssociationSettingsConflict("Settings changed since this form was opened")
        matches = cls._matching_items(items)

        # Validate the entire plan before mutating any entity or inserting rows.
        for option in METHOD_ASSOCIATION_OPTIONS:
            candidates = matches[option.code]
            if len(candidates) > 1:
                raise MethodAssociationDataConflict("Ambiguous saved method associations")
            if not candidates and option.code in normalized_codes:
                if any(cls._name_key(item.name) == cls._name_key(option.name) for item in items):
                    raise MethodAssociationDataConflict("Name is occupied by another code")

        for option in METHOD_ASSOCIATION_OPTIONS:
            candidates = matches[option.code]
            selected = option.code in normalized_codes
            if candidates:
                entity = candidates[0]
                entity.code = option.code
                entity.is_active = selected
                # Keep existing IDs/names used by historical review protocols.
            elif selected:
                await Repo.create(db, school_id=school_id, code=option.code, name=option.name, is_active=True)
        await db.commit()

    @staticmethod
    def _normalize_selected_codes(selected_codes: list[str]) -> set[str]:
        return {code.strip() for code in selected_codes if code and code.strip()}

    @staticmethod
    def _validate_selected_codes(selected_codes: set[str]) -> None:
        if selected_codes - METHOD_ASSOCIATION_CODES:
            raise ValueError("Unknown method association code")
