# app/modules/schools/method_association_dto.py
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class MethodAssociationSettingsItemDTO:
    """
    Один допустимый вариант МО на странице настроек.
    """

    code: str
    name: str
    selected: bool


@dataclass(slots=True)
class MethodAssociationSettingsPageDTO:
    """
    Данные страницы настройки МО школы.
    """

    school_id: int
    options: list[MethodAssociationSettingsItemDTO]


@dataclass(slots=True, frozen=True)
class MethodAssociationSettingsUpdateDTO:
    selected_codes: list[str]
