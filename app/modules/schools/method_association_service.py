# app/modules/schools/method_association_service.py

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.schools.method_association_dto import (
    MethodAssociationSettingsItemDTO,
    MethodAssociationSettingsPageDTO,
)
from app.modules.schools.method_assoc import (
    METHOD_ASSOCIATION_CODES,
    METHOD_ASSOCIATION_OPTIONS,
)
from app.modules.schools.method_association_repo import (
    SchoolMethodAssociationRepository,
)


class SchoolMethodAssociationService:
    """
    Сервис настройки методических объединений школы.
    """

    @classmethod
    async def get_settings_page_data(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
    ) -> MethodAssociationSettingsPageDTO:
        """
        Формирует данные страницы настройки МО школы.
        """

        existing_items = (
            await SchoolMethodAssociationRepository.get_all_by_school(
                db,
                school_id=school_id,
            )
        )

        active_codes = {
            item.code
            for item in existing_items
            if item.code is not None and item.is_active
        }

        options = [
            MethodAssociationSettingsItemDTO(
                code=option.code,
                name=option.name,
                selected=option.code in active_codes,
            )
            for option in METHOD_ASSOCIATION_OPTIONS
        ]

        return MethodAssociationSettingsPageDTO(
            school_id=school_id,
            options=options,
        )

    @classmethod
    async def update_settings(
        cls,
        db: AsyncSession,
        *,
        school_id: int,
        selected_codes: list[str],
    ) -> None:
        """
        Сохраняет выбранные методические объединения школы.

        Выбранные варианты создаются или активируются.
        Невыбранные существующие варианты деактивируются.
        """

        normalized_codes = cls._normalize_selected_codes(
            selected_codes
        )

        cls._validate_selected_codes(normalized_codes)

        existing_items = (
            await SchoolMethodAssociationRepository.get_all_by_school(
                db,
                school_id=school_id,
            )
        )

        existing_by_code = {
            item.code: item
            for item in existing_items
            if item.code
        }

        existing_by_name = {
            item.name.strip().casefold(): item
            for item in existing_items
        }

        for option in METHOD_ASSOCIATION_OPTIONS:
            entity = existing_by_code.get(option.code)

            # Поддержка старых записей, у которых code ещё не заполнен.
            if entity is None:
                entity = existing_by_name.get(
                    option.name.strip().casefold()
                )

            should_be_active = (
                option.code in normalized_codes
            )

            if entity is None:
                if should_be_active:
                    await SchoolMethodAssociationRepository.create(
                        db,
                        school_id=school_id,
                        code=option.code,
                        name=option.name,
                        is_active=True,
                    )

                continue

            entity.code = option.code
            entity.name = option.name
            entity.is_active = should_be_active

        await db.commit()

    @staticmethod
    def _normalize_selected_codes(
        selected_codes: list[str],
    ) -> set[str]:
        """
        Очищает и удаляет дубли переданных кодов.
        """

        return {
            code.strip()
            for code in selected_codes
            if code and code.strip()
        }

    @staticmethod
    def _validate_selected_codes(
        selected_codes: set[str],
    ) -> None:
        """
        Проверяет, что все коды входят в допустимый справочник.
        """

        invalid_codes = (
            selected_codes - METHOD_ASSOCIATION_CODES
        )

        if invalid_codes:
            raise ValueError(
                "Переданы неизвестные методические объединения: "
                + ", ".join(sorted(invalid_codes))
            )
