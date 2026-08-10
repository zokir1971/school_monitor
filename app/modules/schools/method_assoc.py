# app/modules/schools/method_assoc.py
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MethodAssociationOption:
    """
    Допустимый вариант методического объединения.
    """

    code: str
    name: str


METHOD_ASSOCIATION_OPTIONS: tuple[MethodAssociationOption, ...] = (
    MethodAssociationOption(
        code="primary_school",
        name="Бастауыш сынып",
    ),
    MethodAssociationOption(
        code="kazakh_language_literature",
        name="Қазақ тілі мен әдебиеті",
    ),
    MethodAssociationOption(
        code="russian_language_literature",
        name="Орыс тілі мен әдебиеті",
    ),
    MethodAssociationOption(
        code="uzbek_language_literature",
        name="Өзбек тілі мен әдебиеті",
    ),
    MethodAssociationOption(
        code="tajik_language_literature",
        name="Тәжік тілі мен әдебиеті",
    ),
    MethodAssociationOption(
        code="foreign_language",
        name="Шетел тілі",
    ),
    MethodAssociationOption(
        code="mathematics",
        name="Математика",
    ),
    MethodAssociationOption(
        code="informatics",
        name="Информатика",
    ),
    MethodAssociationOption(
        code="mathematics_informatics",
        name="Математика және информатика",
    ),
    MethodAssociationOption(
        code="physics_informatics",
        name="Физика және информатика",
    ),
    MethodAssociationOption(
        code="chemistry_biology",
        name="Химия және биология",
    ),
    MethodAssociationOption(
        code="physics",
        name="Физика",
    ),
    MethodAssociationOption(
        code="chemistry",
        name="Химия",
    ),
    MethodAssociationOption(
        code="biology",
        name="Биология",
    ),
    MethodAssociationOption(
        code="geography",
        name="География",
    ),
    MethodAssociationOption(
        code="history",
        name="Тарих",
    ),
    MethodAssociationOption(
        code="history_geography",
        name="Тарих және география",
    ),
    MethodAssociationOption(
        code="military_physical_education",
        name="АӘД және дене шынықтыру",
    ),
    MethodAssociationOption(
        code="art_labor",
        name="Өнер және еңбек",
    ),
    MethodAssociationOption(
        code="language_subjects",
        name="Тіл пәндері",
    ),
    MethodAssociationOption(
        code="natural_science_mathematics",
        name="Жаратылыстану-математикалық",
    ),
    MethodAssociationOption(
        code="social_humanities",
        name="Қоғамдық-гуманитарлық",
    ),
    MethodAssociationOption(
        code="class_teachers",
        name="Сынып жетекшілерінің әдістемелік бірлестігі",
    ),
)


METHOD_ASSOCIATION_OPTIONS_BY_CODE: dict[
    str,
    MethodAssociationOption,
] = {
    option.code: option
    for option in METHOD_ASSOCIATION_OPTIONS
}


METHOD_ASSOCIATION_CODES: frozenset[str] = frozenset(
    METHOD_ASSOCIATION_OPTIONS_BY_CODE
)
