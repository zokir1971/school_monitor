# app/modules/assessment/helpers/question_bank_form.py
from __future__ import annotations

from app.modules.assessment.helpers.single_choice_score_policy import validate_single_choice_parts
from app.modules.assessment.helpers.multiple_choice_score_policy import validate_multiple_choice_score
from app.modules.assessment.helpers.true_false_score_policy import validate_true_false
from app.modules.assessment.helpers.number_score_policy import validate_number_parts
from app.modules.assessment.helpers.matching_score_policy import validate_matching_score
from app.modules.assessment.helpers.ordering_score_policy import validate_ordering_score
from app.modules.assessment.helpers.formula_score_policy import validate_formula_parts
from app.modules.assessment.helpers.fill_gaps_score_policy import validate_fill_gaps_score

import re
import json
from typing import Any, Callable

from starlette.datastructures import FormData
from dataclasses import dataclass
from decimal import Decimal

from app.modules.assessment.services.question_bank_media_service import validate_media_segment

from app.modules.assessment.helpers.manual_review_criteria import validate_manual_criteria

from app.modules.assessment.helpers.formula_contract_rules import validate_formula_meanings

from app.modules.assessment.enums import (
    AssessmentQuestionType,
)


@dataclass(slots=True, frozen=True)
class QuestionFormContract:
    """
    Question Contract, построенный из HTML-form.

    Это web-adapter DTO.

    Доменная валидация выполняется отдельно
    через AssessmentQuestionValidationService.
    """

    content: dict
    answer_key: dict
    grading_settings: dict


def _required_string(
        form: FormData,
        field_name: str,
        *,
        error_message: str,
) -> str:
    value = form.get(field_name)

    if value is None:
        raise ValueError(error_message)

    normalized = str(value).strip()

    if not normalized:
        raise ValueError(error_message)

    return normalized


def _text_segments(
        text: str,
) -> list[dict[str, str]]:
    """
    Создаёт rich-content из обычного текста.

    Используется как базовый web-adapter,
    пока HTML-editor не передаёт смешанные
    text / latex сегменты напрямую.
    """

    normalized = text.strip()

    if not normalized:
        raise ValueError(
            "Мазмұн бос болмауы керек."
        )

    return [
        {
            "type": "text",
            "text": normalized,
        }
    ]


def _parse_rich_segments(
        raw_value: str,
        *,
        field_name: str,
) -> list[dict[str, Any]]:
    """
    Разбирает JSON, полученный от rich-editor.

    Доменную validation здесь не выполняем.
    Полный Question Contract проверяет
    AssessmentQuestionValidationService.
    """

    try:
        parsed = json.loads(
            raw_value
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{field_name}: "
            "rich-content JSON қате."
        ) from exc

    if not isinstance(
            parsed,
            list,
    ):
        raise ValueError(
            f"{field_name}: "
            "segments тізім болуы керек."
        )

    if not parsed:
        raise ValueError(
            f"{field_name}: "
            "мазмұн бос болмауы керек."
        )

    return parsed


def build_question_text_segments(
        form: FormData,
) -> list[dict[str, Any]]:
    """
    Строит rich-content основного текста вопроса.

    Приоритет:
        question_text_segments — данные rich-editor.

    Fallback:
        text — обычное текстовое поле формы.
    """

    raw_segments = form.get(
        "question_text_segments"
    )

    if (
            isinstance(raw_segments, str)
            and raw_segments.strip()
    ):
        return _parse_rich_segments(
            raw_segments,
            field_name="question_text_segments",
        )

    question_text = _required_string(
        form,
        "text",
        error_message=(
            "Тапсырма мәтінін толтыру қажет."
        ),
    )

    return _text_segments(question_text)


def build_question_plain_text(
        segments: list[dict[str, Any]],
) -> str:
    """
    Создаёт plain-text представление вопроса
    из rich-content segments.
    """

    if not isinstance(segments, list):
        raise ValueError(
            "text_segments тізім болуы керек."
        )

    parts: list[str] = []

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError(
                f"text_segments[{index}] "
                "dict болуы керек."
            )

        segment_type = segment.get("type")

        if segment_type == "image":
            validate_media_segment(segment)
            parts.append("[Сурет]")
            continue

        if segment_type not in {"text", "latex"}:
            raise ValueError(
                f"text_segments[{index}].type "
                "'text' немесе 'latex' болуы керек."
            )

        value = segment.get("text")

        if not isinstance(value, str):
            raise ValueError(
                f"text_segments[{index}].text "
                "мәтін болуы керек."
            )

        parts.append(value)

    result = "".join(parts).strip()

    if not result:
        raise ValueError(
            "Тапсырма мәтінін толтыру қажет."
        )

    return result


def _build_choice_options(
        form: FormData,
) -> list[dict[str, Any]]:
    """
    Преобразует поля A-D
    в content.options Question Contract.

    Поддерживает:

    1. Rich-editor:
       option_a_segments
       option_b_segments
       ...

    2. Обычный text input как fallback:
       option_a
       option_b
       ...

    Доменную validation выполняет
    AssessmentQuestionValidationService.
    """

    options: list[dict[str, Any]] = []

    for value in (
            "A",
            "B",
            "C",
            "D",
    ):
        suffix = value.lower()

        segments_field = (
            f"option_{suffix}_segments"
        )

        raw_segments = form.get(
            segments_field
        )

        if (
                isinstance(
                    raw_segments,
                    str,
                )
                and raw_segments.strip()
        ):
            segments = (
                _parse_rich_segments(
                    raw_segments,
                    field_name=(
                        segments_field
                    ),
                )
            )

        else:
            option_text = (
                _required_string(
                    form,
                    f"option_{suffix}",
                    error_message=(
                        "Барлық жауап "
                        "нұсқаларын "
                        "толтыру қажет."
                    ),
                )
            )

            segments = (
                _text_segments(
                    option_text
                )
            )

        options.append(
            {
                "value": value,
                "segments": segments,
            }
        )

    return options


def _build_single_choice_contract(
        form: FormData,
) -> QuestionFormContract:
    raw = form.get('single_choice_parts')
    if raw is not None:
        if len(str(raw)) > 2000000:
            raise ValueError('Пункты single_choice слишком большие.')
        try:
            payload = json.loads(str(raw))
        except (ValueError, RecursionError) as exc:
            raise ValueError('Проверьте пункты single_choice.') from exc
        if not isinstance(payload,dict) or set(payload) != {'parts','values'}:
            raise ValueError('Нужны пункты и правильные ответы single_choice.')
        content = {'parts':payload['parts']}
        key = {'values':payload['values']}
        grading = {'single_choice_score_policy':'per_part_v1','partial_credit':True}
        validate_single_choice_parts(content,key,grading,max_score=form.get('max_score'),require_parts=True)
        return QuestionFormContract(content=content,answer_key=key,grading_settings=grading)
    options = _build_choice_options(form)

    correct_answer = _required_string(
        form,
        "correct_answer",
        error_message=(
            "Дұрыс жауапты таңдау қажет."
        ),
    ).upper()

    return QuestionFormContract(
        content={
            "options": options,
        },
        answer_key={
            "value": correct_answer,
        },
        grading_settings={},
    )


def _build_multiple_choice_contract(
        form: FormData,
) -> QuestionFormContract:
    options = _build_choice_options(form)

    correct_answers = [
        str(value).strip().upper()
        for value in form.getlist(
            "correct_answers"
        )
        if str(value).strip()
    ]

    # Удаляем дубли, сохраняя порядок.
    correct_answers = list(
        dict.fromkeys(correct_answers)
    )

    if not correct_answers:
        raise ValueError(
            "Кемінде бір дұрыс "
            "жауапты таңдау қажет."
        )

    return QuestionFormContract(
        content={
            "options": options,
        },
        answer_key={
            "values": correct_answers,
        },
        grading_settings={
            "partial_credit": False,
        },
    )


def _build_true_false_contract(
        form: FormData,
) -> QuestionFormContract:
    raw = form.get("true_false_statements")
    if raw is not None:
        try:
            payload = json.loads(str(raw))
        except (ValueError, TypeError) as exc:
            raise ValueError("Не удалось прочитать утверждения.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Утверждения должны быть JSON object.")
        content = {"statements": payload.get("statements"),
                   "labels": {"true": "Дұрыс", "false": "Бұрыс"}}
        key = {"values": payload.get("values")}
        validate_true_false(content, key, max_score=form.get("max_score"), require_statements=True)
        return QuestionFormContract(content=content, answer_key=key, grading_settings={})
    correct_answer = _required_string(
        form,
        "correct_answer",
        error_message=(
            "Дұрыс немесе бұрыс "
            "жауабын таңдау қажет."
        ),
    ).lower()

    if correct_answer == "true":
        correct_value = True

    elif correct_answer == "false":
        correct_value = False

    else:
        raise ValueError(
            "Дұрыс / бұрыс "
            "жауабы қате берілген."
        )

    return QuestionFormContract(
        content={
            "labels": {
                "true": "Дұрыс",
                "false": "Бұрыс",
            },
        },
        answer_key={
            "value": correct_value,
        },
        grading_settings={},
    )


def _build_short_text_contract(
        form: FormData,
) -> QuestionFormContract:
    """
    Строит Question Contract
    для короткого текстового ответа.

    HTML-form может передать несколько
    accepted_answers с одинаковым name.
    """

    accepted_answers = [
        str(value).strip()
        for value in form.getlist(
            "accepted_answers"
        )
        if str(value).strip()
    ]

    # Удаляем точные дубли,
    # сохраняя порядок ввода.
    accepted_answers = list(
        dict.fromkeys(
            accepted_answers
        )
    )

    if not accepted_answers:
        raise ValueError(
            "Кемінде бір қабылданатын "
            "жауапты енгізу қажет."
        )

    return QuestionFormContract(
        content={},
        answer_key={
            "accepted_answers":
                accepted_answers,
        },
        grading_settings={
            "case_sensitive": False,
            "trim_whitespace": True,
        },
    )


def _build_number_contract(
        form: FormData,
) -> QuestionFormContract:
    """
    Строит Question Contract
    для числового ответа.
    """

    raw_parts = form.get("number_parts")
    if raw_parts is not None:
        try:
            payload = json.loads(str(raw_parts))
        except (ValueError, TypeError) as exc:
            raise ValueError("Не удалось прочитать числовые пункты.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Числовые пункты должны быть JSON object.")
        content = {"parts": payload.get("parts")}
        key = {"values": payload.get("values")}
        grading = {"tolerances": payload.get("tolerances", {})}
        validate_number_parts(content, key, grading, max_score=form.get("max_score"), require_parts=True)
        return QuestionFormContract(content=content, answer_key=key, grading_settings=grading)

    raw_value = _required_string(
        form,
        "number_answer",
        error_message=(
            "Дұрыс сандық жауапты "
            "енгізу қажет."
        ),
    )

    try:
        number_value = float(
            raw_value.replace(",", ".")
        )
    except ValueError as exc:
        raise ValueError(
            "Дұрыс сандық жауап "
            "сан болуы керек."
        ) from exc

    raw_unit = form.get(
        "number_unit"
    )

    unit = (
        str(raw_unit).strip()
        if raw_unit is not None
        else ""
    )

    raw_tolerance = form.get(
        "number_tolerance"
    )

    tolerance_text = (
        str(raw_tolerance).strip()
        if raw_tolerance is not None
        else ""
    )

    content: dict = {}

    if unit:
        content["unit"] = unit

    grading_settings: dict = {}

    if tolerance_text:
        try:
            tolerance = float(
                tolerance_text.replace(
                    ",",
                    ".",
                )
            )
        except ValueError as exc:
            raise ValueError(
                "Рұқсат етілген ауытқу "
                "сан болуы керек."
            ) from exc

        if tolerance < 0:
            raise ValueError(
                "Рұқсат етілген ауытқу "
                "0-ден кем болмауы керек."
            )

        grading_settings[
            "tolerance"
        ] = tolerance

    return QuestionFormContract(
        content=content,
        answer_key={
            "value": number_value,
        },
        grading_settings=(
            grading_settings
        ),
    )


def _restore_row_segments(form: FormData, name: str, index: int, text: str) -> list[dict]:
    originals = form.getlist(f"{name}_original_segments")
    if index < len(originals) and str(originals[index]).strip():
        segments = _parse_rich_segments(str(originals[index]), field_name=name)
        if "".join(s.get("text", "") for s in segments).strip() == text:
            return segments
    return _text_segments(text)


def _build_matching_contract(
        form: FormData,
) -> QuestionFormContract:
    """
    Строит Question Contract
    для задания на соответствие.

    HTML-form передаёт строки парами:

        matching_left
        matching_right

    Каждая строка интерфейса означает
    правильное соответствие left -> right.
    """

    raw_pairs = form.get("matching_pairs_payload")
    if raw_pairs is not None:
        try:
            payload = json.loads(str(raw_pairs))
        except (ValueError, TypeError) as exc:
            raise ValueError("Не удалось прочитать пары сопоставления.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Пары должны быть JSON object.")
        content = {"left": payload.get("left"), "right": payload.get("right")}
        key = {"pairs": payload.get("pairs")}
        grading = {"matching_score_policy": "per_pair_v1", "partial_credit": True}
        validate_matching_score(content, key, grading, max_score=form.get("max_score"), require_policy=True)
        return QuestionFormContract(content=content, answer_key=key, grading_settings=grading)

    raw_left_items = form.getlist(
        "matching_left"
    )

    raw_right_items = form.getlist(
        "matching_right"
    )

    # Количество левых и правых значений
    # должно совпадать.
    if (
            len(raw_left_items)
            != len(raw_right_items)
    ):
        raise ValueError(
            "Сәйкестендіру тапсырмасының "
            "сол және оң жақ элементтерінің "
            "саны сәйкес келмейді."
        )

    if not raw_left_items:
        raise ValueError(
            "Кемінде бір сәйкестендіру "
            "жұбын енгізу қажет."
        )

    left: list[dict[str, str]] = []
    right: list[dict[str, str]] = []
    pairs: list[dict[str, str]] = []

    for index, (
            raw_left,
            raw_right,
    ) in enumerate(
        zip(
            raw_left_items,
            raw_right_items,
            strict=True,
        ),
        start=1,
    ):
        left_text = str(
            raw_left
        ).strip()

        right_text = str(
            raw_right
        ).strip()

        if not left_text:
            raise ValueError(
                f"{index}-жұптың сол жақ "
                "мәнін толтыру қажет."
            )

        if not right_text:
            raise ValueError(
                f"{index}-жұптың оң жақ "
                "мәнін толтыру қажет."
            )

        left_value = f"L{index}"
        right_value = f"R{index}"

        left.append(
            {
                "value": left_value,
                "segments": (
                    _restore_row_segments(form, "matching_left", index - 1, left_text)
                ),
            }
        )

        right.append(
            {
                "value": right_value,
                "segments": (
                    _restore_row_segments(form, "matching_right", index - 1, right_text)
                ),
            }
        )
        pairs.append(
            {
                "left": left_value,
                "right": right_value,
            }
        )

    return QuestionFormContract(
        content={
            "left": left,
            "right": right,
        },
        answer_key={
            "pairs": pairs,
        },
        grading_settings={
            "partial_credit": False,
        },
    )


def _build_ordering_contract(
        form: FormData,
) -> QuestionFormContract:
    """
    Строит Question Contract
    для задания ORDERING.

    Учитель вводит элементы сразу
    в правильном порядке.

    HTML-form передаёт несколько полей:

        ordering_item

    Порядок полей в форме является
    правильным порядком ответа.
    """

    raw_ordering = form.get("ordering_items_payload")
    if raw_ordering is not None:
        try:
            payload = json.loads(str(raw_ordering))
        except (ValueError, TypeError) as exc:
            raise ValueError("Не удалось прочитать элементы порядка.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Порядок должен быть JSON object.")
        content = {"items": payload.get("items")}
        key = {"order": payload.get("order")}
        grading = {"ordering_score_policy": "per_position_v1", "partial_credit": True}
        validate_ordering_score(content, key, grading, max_score=form.get("max_score"), require_policy=True)
        return QuestionFormContract(content=content, answer_key=key, grading_settings=grading)

    raw_items = form.getlist(
        "ordering_item"
    )

    items_text = [
        str(value).strip()
        for value in raw_items
        if str(value).strip()
    ]

    if len(items_text) < 2:
        raise ValueError(
            "Ретін анықтау тапсырмасы үшін "
            "кемінде екі элемент енгізу қажет."
        )

    items: list[
        dict[str, str]
    ] = []

    correct_order: list[str] = []

    for index, item_text in enumerate(
            items_text,
            start=1,
    ):
        item_value = f"I{index}"

        items.append(
            {
                "value": item_value,
                "segments": (
                    _restore_row_segments(form, "ordering_item",
                                          [i for i, raw in enumerate(raw_items) if str(raw).strip()][index - 1],
                                          item_text)
                ),
            }
        )

        correct_order.append(
            item_value
        )

    return QuestionFormContract(
        content={
            "items": items,
        },
        answer_key={
            "order": correct_order,
        },
        grading_settings={
            "partial_credit": False,
        },
    )


_FILL_GAP_PATTERN = re.compile(
    r"\[\[(.+?)]]"
)


def _build_fill_gaps_contract(
        form: FormData,
) -> QuestionFormContract:
    """
    Строит Question Contract для FILL_GAPS.

    HTML-form:

        fill_gaps_text
            Текст задания с пропусками:

                Компьютер ақпаратты
                [[өңдейді]] және
                [[сақтайды]].

        fill_gaps_mode
            text_input | word_bank

        fill_gap_alternatives_G1
        fill_gap_alternatives_G2
        ...

            Необязательные альтернативные
            правильные ответы.

        fill_word_bank
            Дополнительные варианты для
            режима word_bank.
    """

    rich_payload = form.get("fill_gaps_rich_payload")
    if rich_payload:
        try:
            payload = json.loads(str(rich_payload))
            content, key = payload["content"], payload["answer_key"]
            if not isinstance(content, dict) or not isinstance(key, dict):
                raise ValueError("Invalid rich bank payload")
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("Не удалось прочитать банк формул и символов.") from exc
        if content.get("word_bank_format") != "rich_v1" or form.get("fill_gaps_mode") != "word_bank":
            raise ValueError("Неверный режим банка формул.")
        grading = {"fill_gaps_score_policy": "per_gap_v1", "partial_credit": True,
                   "case_sensitive": False, "trim_whitespace": True}
        validate_fill_gaps_score(content, key, grading, max_score=form.get("max_score"), require_policy=True)
        return QuestionFormContract(content=content, answer_key=key, grading_settings=grading)

    legacy_edit = False
    previous = {}
    if form.get("initial_question_type") == AssessmentQuestionType.FILL_GAPS.value:
        try:
            previous = json.loads(str(form.get("initial_grading_settings") or "{}"))
        except (ValueError, TypeError) as exc:
            raise ValueError("Не удалось прочитать прежние настройки оценивания.") from exc
        if not isinstance(previous, dict):
            raise ValueError("Прежние настройки должны быть JSON object.")
        legacy_edit = "fill_gaps_score_policy" not in previous
        if not legacy_edit and previous["fill_gaps_score_policy"] != "per_gap_v1":
            raise ValueError("Неизвестная версия оценивания пропусков.")

    # =====================================================
    # MODE
    # =====================================================

    input_mode = _required_string(
        form,
        "fill_gaps_mode",
        error_message=(
            "Бос орындарды толтыру "
            "режимін таңдау қажет."
        ),
    )

    if input_mode not in {
        "text_input",
        "word_bank",
    }:
        raise ValueError(
            "Бос орындарды толтыру "
            "режимі қате берілген."
        )

    # =====================================================
    # SOURCE TEXT
    # =====================================================

    source_text = _required_string(
        form,
        "fill_gaps_text",
        error_message=(
            "Бос орындары бар мәтінді "
            "енгізу қажет."
        ),
    )

    if not legacy_edit:
        from app.modules.assessment.helpers.fill_gaps_score_policy import validate_fill_source
        validate_fill_source(source_text)

    matches = list(
        _FILL_GAP_PATTERN.finditer(
            source_text
        )
    )

    if not matches:
        raise ValueError(
            "Мәтінде кемінде бір "
            "[[дұрыс жауап]] болуы қажет."
        )

    # =====================================================
    # SEGMENTS + ANSWER KEY
    # =====================================================

    segments: list[dict] = []

    gaps: dict[
        str,
        dict[str, list[str]],
    ] = {}

    cursor = 0

    for index, match in enumerate(
            matches,
            start=1,
    ):
        # ---------------------------------------------
        # TEXT BEFORE GAP
        # ---------------------------------------------

        text_before = source_text[
                      cursor:match.start()
                      ]

        if text_before:
            segments.append(
                {
                    "type": "text",
                    "text": text_before,
                }
            )

        # ---------------------------------------------
        # GAP
        # ---------------------------------------------

        gap_id = f"G{index}"

        primary_answer = (
            match.group(1) if not legacy_edit and previous.get("trim_whitespace", True) is False
            else match.group(1).strip()
        )

        if not primary_answer:
            raise ValueError(
                f"{gap_id} бос орнының "
                "дұрыс жауабы бос болмауы керек."
            )

        segments.append(
            {
                "type": "gap",
                "gap_id": gap_id,
            }
        )

        # ---------------------------------------------
        # ACCEPTED ANSWERS
        # ---------------------------------------------

        accepted_answers = [
            primary_answer
        ]

        alternative_field = (
            f"fill_gap_alternatives_{gap_id}"
        )

        alternatives = [
            (str(value) if not legacy_edit and previous.get("trim_whitespace", True) is False else str(value).strip())
            for value in form.getlist(
                alternative_field
            )
            if str(value).strip()
        ]

        accepted_answers.extend(
            alternatives
        )

        # Удаляем точные дубли,
        # сохраняя порядок.
        accepted_answers = list(
            dict.fromkeys(
                accepted_answers
            )
        )

        gaps[gap_id] = {
            "accepted_answers":
                accepted_answers,
        }

        cursor = match.end()

    # =====================================================
    # FINAL TEXT
    # =====================================================

    text_after = source_text[
                 cursor:
                 ]

    if text_after:
        segments.append(
            {
                "type": "text",
                "text": text_after,
            }
        )

    # =====================================================
    # CONTENT
    # =====================================================

    content: dict = {
        "input_mode": input_mode,
        "segments": segments,
    }

    # =====================================================
    # WORD BANK
    # =====================================================

    if input_mode == "word_bank":
        word_bank: list[str] = []

        # Сначала добавляем все правильные ответы.
        for gap_settings in gaps.values():
            word_bank.extend(
                gap_settings[
                    "accepted_answers"
                ]
            )

        # Затем дополнительные ложные
        # или отвлекающие варианты.
        extra_word_bank = [
            str(value).strip()
            for value in form.getlist(
                "fill_word_bank"
            )
            if str(value).strip()
        ]

        word_bank.extend(
            extra_word_bank
        )

        # Удаляем дубли,
        # сохраняя порядок.
        word_bank = list(
            dict.fromkeys(
                word_bank
            )
        )

        if not word_bank:
            raise ValueError(
                "Сөздер банкі бос "
                "болмауы керек."
            )

        content[
            "word_bank"
        ] = word_bank

    # =====================================================
    # RESULT
    # =====================================================

    return QuestionFormContract(
        content=content,

        answer_key={
            "gaps": gaps,
        },

        grading_settings={
            "case_sensitive": False,
            "trim_whitespace": True,
            "partial_credit": False if legacy_edit else True,
            **({} if legacy_edit else {"fill_gaps_score_policy": "per_gap_v1"}),
        },
    )


def _build_formula_contract(form: FormData) -> QuestionFormContract:
    raw_parts = form.get("formula_parts_payload")
    if raw_parts:
        try:
            payload = json.loads(str(raw_parts))
            content, key = {"parts": payload["parts"]}, {"parts": payload["answers"]}
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError("Не удалось прочитать пункты формул.") from exc
        grading = {"formula_score_policy": "per_part_v1", "partial_credit": True,
                   "variable_meanings_required": True, "equivalence_mode": "exact", "trim_whitespace": True}
        if form.get("initial_question_type") == AssessmentQuestionType.FORMULA.value:
            try:
                previous_grading = json.loads(str(form.get("initial_grading_settings") or "{}"))
                if not isinstance(previous_grading, dict):
                    raise ValueError("Invalid previous settings")
                if previous_grading.get("formula_score_policy") == "per_part_v1":
                    grading["trim_whitespace"] = previous_grading.get("trim_whitespace", True)
            except (ValueError, TypeError) as exc:
                raise ValueError("Не удалось прочитать настройки формул.") from exc
        validate_formula_parts(content, key, grading, max_score=form.get("max_score"), require_parts=True)
        return QuestionFormContract(content=content, answer_key=key, grading_settings=grading)
    # Existing single-formula tasks keep their old editor and scoring contract.
    if form.get("initial_question_type") != AssessmentQuestionType.FORMULA.value:
        raise ValueError("Новый formula требует пункты по максимальному баллу. Обновите страницу и редактор.")
    try:
        previous = json.loads(str(form.get("initial_grading_settings") or "{}"))
        previous_content = json.loads(str(form.get("initial_content") or "{}"))
    except (ValueError, TypeError) as exc:
        raise ValueError("Не удалось прочитать исходный формат формул.") from exc
    if not isinstance(previous, dict) or not isinstance(previous_content, dict) or "formula_score_policy" in previous or "parts" in previous_content:
        raise ValueError("Для многопунктной формулы отсутствует payload. Сохранение заблокировано.")
    expression = _required_string(form, "formula_answer", error_message="Дұрыс формуланы енгізіңіз.")
    symbols = form.getlist("formula_symbol")
    labels = form.getlist("formula_meaning")
    if len(symbols) != len(labels) or not 1 <= len(symbols) <= 30:
        raise ValueError("Формула белгіленулерін және шамаларын енгізіңіз.")
    variables, options, meanings = [], [], {}
    label_ids = {}

    def add_option(label):
        if not isinstance(label, str) or not label.strip():
            raise ValueError("Шама атауын толтырыңыз.")
        label = label.strip()
        if label not in label_ids:
            key = f"M{len(options) + 1}"
            options.append({"value": key, "label": label})
            label_ids[label] = key
        return label_ids[label]

    for symbol, label in zip(symbols, labels):
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("Формула белгіленуін толтырыңыз.")
        symbol = symbol.strip()
        if symbol in meanings:
            raise ValueError("Формула белгіленулері қайталанбауы керек.")
        variables.append(symbol)
        meanings[symbol] = add_option(label)
    for label in form.getlist("formula_distractor"):
        if str(label).strip():
            add_option(label)
    content = {"variables": variables, "meaning_options": options}
    target = str(form.get("formula_target_variable", "")).strip()
    if target:
        content["target_variable"] = target
    answer_key = {"expression": expression, "variable_meanings": meanings}
    grading = {"equivalence_mode": "exact", "trim_whitespace": True, "variable_meanings_required": True}
    validate_formula_meanings(content, answer_key, grading)
    return QuestionFormContract(content=content, answer_key=answer_key, grading_settings=grading)


def _build_manual_review_contract(form: FormData) -> QuestionFormContract:
    names = ("manual_criterion_id", "manual_criterion_title", "manual_criterion_description", "manual_criterion_score")
    columns = [form.getlist(name) for name in names]
    if len({len(column) for column in columns}) != 1:
        raise ValueError("Критерий өрістері сәйкес емес.")
    criteria = [dict(zip(("id", "title", "description", "max_score"), values))
                for values in zip(*columns)]
    criteria = validate_manual_criteria(criteria, max_score=form.get("max_score", ""))
    return QuestionFormContract(
        content={"response_format": "text"},
        answer_key={},
        grading_settings={"manual_review": True, "criteria": criteria},
    )


def _build_image_choice_contract(form: FormData) -> QuestionFormContract:
    options = []
    for value in "ABCD":
        prefix = f"image_option_{value.lower()}"
        key = _required_string(form, f"{prefix}_key", error_message=f"{value}: суретті жүктеңіз.")
        option = {"value": value, "object_key": key, "alt": str(form.get(f"{prefix}_alt", "")).strip()}
        validate_media_segment(option)
        options.append(option)
    correct = _required_string(form, "image_correct_answer", error_message="Дұрыс суретті таңдаңыз.")
    if correct not in "ABCD" or len(correct) != 1:
        raise ValueError("Дұрыс жауап A, B, C немесе D болуы керек.")
    return QuestionFormContract(content={"options": options}, answer_key={"value": correct}, grading_settings={})


QuestionFormBuilder = Callable[
    [FormData],
    QuestionFormContract,
]

_QUESTION_FORM_BUILDERS: dict[
    AssessmentQuestionType,
    QuestionFormBuilder,
] = {
    AssessmentQuestionType.SINGLE_CHOICE:
        _build_single_choice_contract,

    AssessmentQuestionType.MULTIPLE_CHOICE:
        _build_multiple_choice_contract,

    AssessmentQuestionType.TRUE_FALSE:
        _build_true_false_contract,

    AssessmentQuestionType.SHORT_TEXT:
        _build_short_text_contract,

    AssessmentQuestionType.NUMBER:
        _build_number_contract,

    AssessmentQuestionType.MATCHING:
        _build_matching_contract,

    AssessmentQuestionType.ORDERING:
        _build_ordering_contract,

    AssessmentQuestionType.FILL_GAPS:
        _build_fill_gaps_contract,

    AssessmentQuestionType.FORMULA:
        _build_formula_contract,

    AssessmentQuestionType.IMAGE_CHOICE:
        _build_image_choice_contract,

    AssessmentQuestionType.MANUAL_REVIEW:
        _build_manual_review_contract,
}


def build_question_form_contract(
        *,
        question_type: AssessmentQuestionType,
        form: FormData,
) -> QuestionFormContract:
    """
    Выбирает web-builder для типа задания.

    Здесь выполняется только преобразование
    HTML-form -> Question Contract.

    Проверка самого Question Contract
    остаётся обязанностью доменного
    AssessmentQuestionValidationService.
    """

    from .element_scoring import POLICY, COUNTED, parameters, maximum, policy_score, clean_grading, validate_elements
    if form.get('element_score_policy') == POLICY:
        values=dict(form)
        meta=parameters(question_type.value,values)
        if Decimal(str(form.get('max_score')))!=maximum(meta):raise ValueError('Максимальный балл не совпадает с расчётом / Ең жоғары балл есепке сәйкес емес.')
        entries=[(k,v) for k,v in form.multi_items() if k not in {'element_score_policy','max_score'}]
        entries.append(('max_score',str(policy_score(question_type.value,meta,form.get('max_score')))))
        for index,(k,v) in enumerate(entries):
            if k=='initial_grading_settings':entries[index]=(k,json.dumps(clean_grading(json.loads(v or '{}'))))
        contract=build_question_form_contract(question_type=question_type,form=FormData(entries))
        grading={**contract.grading_settings,**meta}
        if question_type.value in COUNTED:grading["partial_credit"]=True
        validate_elements(question_type.value,contract.content,contract.answer_key,grading,form.get('max_score'))
        return QuestionFormContract(content=contract.content,answer_key=contract.answer_key,grading_settings=grading)

    builder = _QUESTION_FORM_BUILDERS.get(
        question_type
    )

    if builder is None:
        raise ValueError(
            "Бұл тапсырма түрі "
            "мұғалім конструкторында "
            "әзірге қолдау таппайды."
        )

    contract = builder(form)

    def initial_object(name: str) -> dict | None:
        raw = form.get(name)
        if raw is None:
            return None
        try:
            value = json.loads(str(raw))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{name}: JSON қате.") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{name}: JSON object болуы керек.")
        return value

    same_type = form.get("initial_question_type") == question_type.value
    original_content = initial_object("initial_content") if same_type else None
    original_grading = initial_object("initial_grading_settings") if same_type else None
    content = {**(original_content or {}), **contract.content}
    if question_type == AssessmentQuestionType.TRUE_FALSE and original_content and "labels" in original_content:
        content["labels"] = original_content["labels"]
    # Removing an optional number unit must remove the old value as well.
    if question_type == AssessmentQuestionType.NUMBER and "unit" not in contract.content:
        content.pop("unit", None)
    if question_type == AssessmentQuestionType.FILL_GAPS and content.get("input_mode") != "word_bank":
        content.pop("word_bank", None)
        content.pop("word_bank_format", None)
    if question_type == AssessmentQuestionType.FORMULA:
        if "parts" in contract.content:
            for name in ("variables", "meaning_options", "target_variable"):
                content.pop(name, None)
        elif "target_variable" not in contract.content:
            content.pop("target_variable", None)
    grading = original_grading if original_grading is not None else contract.grading_settings
    grading = dict(grading)
    if question_type in {AssessmentQuestionType.MANUAL_REVIEW, AssessmentQuestionType.FORMULA}:
        grading.update(contract.grading_settings)
    if question_type == AssessmentQuestionType.SINGLE_CHOICE:
        if 'parts' in contract.content:
            content.pop('options',None)
            grading.update(contract.grading_settings)
        else:
            content.pop('parts',None)
            grading.pop('single_choice_score_policy',None)
        validate_single_choice_parts(content,contract.answer_key,grading,max_score=form.get('max_score'))
    if question_type == AssessmentQuestionType.NUMBER:
        grading.pop("tolerance", None)
        grading.pop("tolerances", None)
        grading.update(contract.grading_settings)
        if "parts" not in contract.content:
            content.pop("parts", None)
        validate_number_parts(content, contract.answer_key, grading, max_score=form.get("max_score"))
    if question_type == AssessmentQuestionType.MULTIPLE_CHOICE:
        validate_multiple_choice_score(content=content, answer_key=contract.answer_key,
                                       max_score=form.get("max_score"))
    if question_type == AssessmentQuestionType.TRUE_FALSE:
        if "statements" not in contract.content:
            content.pop("statements", None)
        validate_true_false(content, contract.answer_key, max_score=form.get("max_score"))
    answer_key = contract.answer_key
    if question_type == AssessmentQuestionType.FORMULA:
        validate_formula_parts(content, answer_key, grading, max_score=form.get("max_score"))
    if question_type == AssessmentQuestionType.MATCHING:
        if "matching_score_policy" in contract.grading_settings:
            grading.update(contract.grading_settings)
        validate_matching_score(content, answer_key, grading, max_score=form.get("max_score"))
        if grading.get("matching_score_policy") == "per_pair_v1" and not same_type:
            from app.modules.assessment.helpers.matching_score_policy import shuffle_new_matching
            content, answer_key = shuffle_new_matching(content, answer_key)
    if question_type == AssessmentQuestionType.ORDERING:
        if "ordering_score_policy" in contract.grading_settings:
            grading.update(contract.grading_settings)
        validate_ordering_score(content, answer_key, grading, max_score=form.get("max_score"))
        if grading.get("ordering_score_policy") == "per_position_v1" and not same_type:
            from app.modules.assessment.helpers.ordering_score_policy import shuffle_new_ordering
            content, answer_key = shuffle_new_ordering(content, answer_key)
    if question_type == AssessmentQuestionType.FILL_GAPS:
        if "fill_gaps_score_policy" in contract.grading_settings:
            grading.update(fill_gaps_score_policy="per_gap_v1", partial_credit=True)
        validate_fill_gaps_score(content, answer_key, grading, max_score=form.get("max_score"))
    return QuestionFormContract(content=content, answer_key=answer_key, grading_settings=grading)
