# app/modules/assessment/services/assessment_question_validation_service.py
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

from app.modules.assessment.services.question_bank_media_service import validate_media_segment

from app.modules.assessment.helpers.manual_review_criteria import validate_manual_criteria

from app.modules.assessment.helpers.formula_contract_rules import validate_formula_meanings

from collections.abc import Mapping
from numbers import Real
from typing import Any

from app.modules.assessment.enums import AssessmentQuestionType


class AssessmentQuestionValidationService:
    """
    Проверяет внутренний Question Contract.

    Сервис:
        - не работает с БД;
        - не использует Repository;
        - не изменяет входные данные;
        - не выполняет grading;
        - не проверяет answer_data ученика.

    Проверяются:
        content
        answer_key
        grading_settings

    Детальная проверка answer_data относится к execution/grading layer.
    """

    @classmethod
    def validate_authoring(cls, *, question_type, content, answer_key, grading_settings, max_score) -> None:
        """Creation/editing/review policy; validate() keeps historical structural semantics."""
        from app.modules.assessment.helpers.element_scoring import weighted, validate_elements, clean_grading
        if weighted(grading_settings):
            score=validate_elements(question_type.value,content,answer_key,grading_settings,max_score)
            return cls.validate_authoring(question_type=question_type,content=content,answer_key=answer_key,
                grading_settings=clean_grading(grading_settings),max_score=score)

        cls.validate(question_type=question_type, content=content, answer_key=answer_key,
                     grading_settings=grading_settings)
        if question_type == AssessmentQuestionType.SINGLE_CHOICE:
            validate_single_choice_parts(content, answer_key, grading_settings, max_score=max_score)
        if question_type == AssessmentQuestionType.MULTIPLE_CHOICE:
            validate_multiple_choice_score(content=content, answer_key=answer_key, max_score=max_score)
        if question_type == AssessmentQuestionType.TRUE_FALSE:
            validate_true_false(content, answer_key, max_score=max_score)
        if question_type == AssessmentQuestionType.NUMBER:
            validate_number_parts(content, answer_key, grading_settings, max_score=max_score)
        if question_type == AssessmentQuestionType.MATCHING:
            validate_matching_score(content, answer_key, grading_settings, max_score=max_score)
        if question_type == AssessmentQuestionType.ORDERING:
            validate_ordering_score(content, answer_key, grading_settings, max_score=max_score)
        if question_type == AssessmentQuestionType.FILL_GAPS:
            validate_fill_gaps_score(content, answer_key, grading_settings, max_score=max_score)
        if question_type == AssessmentQuestionType.FORMULA:
            validate_formula_parts(content, answer_key, grading_settings, max_score=max_score)
        if question_type == AssessmentQuestionType.MANUAL_REVIEW:
            validate_manual_criteria(grading_settings.get("criteria"), max_score=max_score)

    @classmethod
    def validate(
        cls,
        *,
        question_type: AssessmentQuestionType,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        cls._validate_root_objects(
            content=content,
            answer_key=answer_key,
            grading_settings=grading_settings,
        )

        validators = {
            AssessmentQuestionType.SINGLE_CHOICE:
                cls._validate_single_choice,

            AssessmentQuestionType.MULTIPLE_CHOICE:
                cls._validate_multiple_choice,

            AssessmentQuestionType.TRUE_FALSE:
                cls._validate_true_false,

            AssessmentQuestionType.SHORT_TEXT:
                cls._validate_short_text,

            AssessmentQuestionType.NUMBER:
                cls._validate_number,

            AssessmentQuestionType.MATCHING:
                cls._validate_matching,

            AssessmentQuestionType.ORDERING:
                cls._validate_ordering,

            AssessmentQuestionType.FILL_GAPS:
                cls._validate_fill_gaps,

            AssessmentQuestionType.FORMULA:
                cls._validate_formula,

            AssessmentQuestionType.IMAGE_CHOICE:
                cls._validate_image_choice,

            AssessmentQuestionType.MANUAL_REVIEW:
                cls._validate_manual_review,
        }

        validator = validators.get(question_type)

        if validator is None:
            raise ValueError(
                f"Unsupported question_type: {question_type!r}."
            )

        validator(
            content=content,
            answer_key=answer_key,
            grading_settings=grading_settings,
        )

    # =========================================================
    # ROOT
    # =========================================================

    @staticmethod
    def _validate_root_objects(
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        if not isinstance(content, dict):
            raise ValueError(
                "content must be dict."
            )

        if not isinstance(answer_key, dict):
            raise ValueError(
                "answer_key must be dict."
            )

        if not isinstance(grading_settings, dict):
            raise ValueError(
                "grading_settings must be dict."
            )

    # =========================================================
    # SINGLE CHOICE
    # =========================================================

    @classmethod
    def _validate_single_choice(
            cls,
            *,
            content: dict[str, Any],
            answer_key: dict[str, Any],
            grading_settings: dict[str, Any],
    ) -> None:
        if "parts" in content or "single_choice_score_policy" in grading_settings:
            validate_single_choice_parts(content, answer_key, grading_settings)
            return
        _ = grading_settings

        options = cls._validate_options(
            content=content,
            minimum=2,
        )

        cls._reject_secret_fields(
            options=options,
        )

        correct_value = cls._require_non_empty_string(
            answer_key,
            "value",
            owner="answer_key",
        )

        option_values = {
            option["value"]
            for option in options
        }

        if correct_value not in option_values:
            raise ValueError(
                "answer_key.value must reference "
                "an existing content option."
            )

    # =========================================================
    # MULTIPLE CHOICE
    # =========================================================

    @classmethod
    def _validate_multiple_choice(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        options = cls._validate_options(
            content=content,
            minimum=2,
        )

        cls._reject_secret_fields(
            options=options,
        )

        values = answer_key.get("values")

        if not isinstance(values, list):
            raise ValueError(
                "answer_key.values must be list."
            )

        if not values:
            raise ValueError(
                "answer_key.values must not be empty."
            )

        cls._validate_unique_string_list(
            values,
            field_name="answer_key.values",
        )

        option_values = {
            option["value"]
            for option in options
        }

        unknown_values = [
            value
            for value in values
            if value not in option_values
        ]

        if unknown_values:
            raise ValueError(
                "answer_key.values contains "
                "unknown option values."
            )

        cls._validate_optional_bool(
            grading_settings,
            "partial_credit",
        )

    # =========================================================
    # TRUE / FALSE
    # =========================================================

    @classmethod
    def _validate_true_false(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        _ = grading_settings
        labels = content.get("labels")

        if labels is not None:
            if not isinstance(labels, dict):
                raise ValueError(
                    "content.labels must be dict."
                )

            for key in ("true", "false"):
                cls._require_non_empty_string(
                    labels,
                    key,
                    owner="content.labels",
                )

        validate_true_false(content, answer_key)

    # =========================================================
    # SHORT TEXT
    # =========================================================

    @classmethod
    def _validate_short_text(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        _ = content
        accepted_answers = answer_key.get(
            "accepted_answers"
        )

        if not isinstance(
            accepted_answers,
            list,
        ):
            raise ValueError(
                "answer_key.accepted_answers "
                "must be list."
            )

        if not accepted_answers:
            raise ValueError(
                "answer_key.accepted_answers "
                "must not be empty."
            )

        cls._validate_unique_string_list(
            accepted_answers,
            field_name=(
                "answer_key.accepted_answers"
            ),
        )

        cls._validate_optional_bool(
            grading_settings,
            "case_sensitive",
        )

        cls._validate_optional_bool(
            grading_settings,
            "trim_whitespace",
        )

    # =========================================================
    # NUMBER
    # =========================================================

    @classmethod
    def _validate_number(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        if "parts" in content:
            validate_number_parts(content, answer_key, grading_settings)
            return
        if "unit" in content:
            unit = content["unit"]

            if not isinstance(unit, str):
                raise ValueError(
                    "content.unit must be string."
                )

            if not unit.strip():
                raise ValueError(
                    "content.unit must not be empty."
                )

        value = answer_key.get("value")

        cls._validate_real_number(
            value,
            field_name="answer_key.value",
        )

        if "tolerance" in grading_settings:
            tolerance = grading_settings[
                "tolerance"
            ]

            cls._validate_real_number(
                tolerance,
                field_name=(
                    "grading_settings.tolerance"
                ),
            )

            if tolerance < 0:
                raise ValueError(
                    "grading_settings.tolerance "
                    "must be >= 0."
                )

    # =========================================================
    # MATCHING
    # =========================================================

    @classmethod
    def _validate_matching(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        if "matching_score_policy" in grading_settings:
            validate_matching_score(content, answer_key, grading_settings)
            return
        left = cls._validate_named_items(
            content.get("left"),
            field_name="content.left",
            minimum=1,
        )

        right = cls._validate_named_items(
            content.get("right"),
            field_name="content.right",
            minimum=1,
        )

        cls._reject_secret_fields(
            options=left,
        )

        cls._reject_secret_fields(
            options=right,
        )

        pairs = answer_key.get("pairs")

        if not isinstance(pairs, list):
            raise ValueError(
                "answer_key.pairs must be list."
            )

        if not pairs:
            raise ValueError(
                "answer_key.pairs must not be empty."
            )

        left_values = {
            item["value"]
            for item in left
        }

        right_values = {
            item["value"]
            for item in right
        }

        seen_left: set[str] = set()
        seen_pairs: set[tuple[str, str]] = set()

        for index, pair in enumerate(pairs):
            if not isinstance(pair, dict):
                raise ValueError(
                    "Each answer_key.pairs item "
                    "must be dict."
                )

            left_value = (
                cls._require_non_empty_string(
                    pair,
                    "left",
                    owner=(
                        f"answer_key.pairs[{index}]"
                    ),
                )
            )

            right_value = (
                cls._require_non_empty_string(
                    pair,
                    "right",
                    owner=(
                        f"answer_key.pairs[{index}]"
                    ),
                )
            )

            if left_value not in left_values:
                raise ValueError(
                    "answer_key.pairs contains "
                    "unknown left value."
                )

            if right_value not in right_values:
                raise ValueError(
                    "answer_key.pairs contains "
                    "unknown right value."
                )

            pair_key = (
                left_value,
                right_value,
            )

            if pair_key in seen_pairs:
                raise ValueError(
                    "Duplicate matching pair "
                    "is not allowed."
                )

            if left_value in seen_left:
                raise ValueError(
                    "Each matching left value "
                    "may appear only once."
                )

            seen_pairs.add(pair_key)
            seen_left.add(left_value)

        if seen_left != left_values:
            raise ValueError(
                "Every content.left item must "
                "have a matching pair."
            )

        cls._validate_optional_bool(
            grading_settings,
            "partial_credit",
        )

    # =========================================================
    # ORDERING
    # =========================================================

    @classmethod
    def _validate_ordering(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        if "ordering_score_policy" in grading_settings:
            validate_ordering_score(content, answer_key, grading_settings)
            return
        items = cls._validate_named_items(
            content.get("items"),
            field_name="content.items",
            minimum=2,
        )

        cls._reject_secret_fields(
            options=items,
        )

        correct_order = answer_key.get(
            "order"
        )

        if not isinstance(
            correct_order,
            list,
        ):
            raise ValueError(
                "answer_key.order must be list."
            )

        cls._validate_unique_string_list(
            correct_order,
            field_name="answer_key.order",
        )

        item_values = {
            item["value"]
            for item in items
        }

        if set(correct_order) != item_values:
            raise ValueError(
                "answer_key.order must contain "
                "every content.items value "
                "exactly once."
            )

        cls._validate_optional_bool(
            grading_settings,
            "partial_credit",
        )

    # =========================================================
    # FILL GAPS
    # =========================================================

    @classmethod
    def _validate_fill_gaps(
            cls,
            *,
            content: dict[str, Any],
            answer_key: dict[str, Any],
            grading_settings: dict[str, Any],
    ) -> None:
        """
        Проверяет Question Contract для FILL_GAPS.

        Поддерживаемые режимы:

            text_input
                Ученик самостоятельно вводит
                ответ в каждый пропуск.

            word_bank
                Ученик выбирает ответ из
                общего банка вариантов.

        Правильные ответы всегда находятся
        только в answer_key и не должны
        попадать в student-visible content.
        """

        if "fill_gaps_score_policy" in grading_settings:
            validate_fill_gaps_score(content, answer_key, grading_settings)
            return

        # =====================================================
        # INPUT MODE
        # =====================================================

        input_mode = content.get(
            "input_mode"
        )

        if not isinstance(
                input_mode,
                str,
        ):
            raise ValueError(
                "content.input_mode "
                "must be string."
            )

        if input_mode not in {
            "text_input",
            "word_bank",
        }:
            raise ValueError(
                "content.input_mode must be "
                "'text_input' or 'word_bank'."
            )

        # =====================================================
        # SEGMENTS
        # =====================================================

        segments = content.get(
            "segments"
        )

        if not isinstance(
                segments,
                list,
        ):
            raise ValueError(
                "content.segments must be list."
            )

        if not segments:
            raise ValueError(
                "content.segments must not be empty."
            )

        gap_ids: list[str] = []

        for index, segment in enumerate(
                segments
        ):
            if not isinstance(
                    segment,
                    dict,
            ):
                raise ValueError(
                    "Each content.segments item "
                    "must be dict."
                )

            segment_type = segment.get(
                "type"
            )

            # ---------------------------------------------
            # TEXT SEGMENT
            # ---------------------------------------------

            if segment_type == "text":
                cls._require_non_empty_string(
                    segment,
                    "text",
                    owner=(
                        f"content.segments[{index}]"
                    ),
                )

            # ---------------------------------------------
            # GAP SEGMENT
            # ---------------------------------------------

            elif segment_type == "gap":
                gap_id = (
                    cls._require_non_empty_string(
                        segment,
                        "gap_id",
                        owner=(
                            f"content.segments[{index}]"
                        ),
                    )
                )

                gap_ids.append(
                    gap_id
                )

            # ---------------------------------------------
            # UNKNOWN SEGMENT
            # ---------------------------------------------

            else:
                raise ValueError(
                    "content.segments type must "
                    "be 'text' or 'gap'."
                )

        # =====================================================
        # GAP IDS
        # =====================================================

        if not gap_ids:
            raise ValueError(
                "FILL_GAPS must contain "
                "at least one gap."
            )

        if len(gap_ids) != len(
                set(gap_ids)
        ):
            raise ValueError(
                "Duplicate gap_id "
                "is not allowed."
            )

        # =====================================================
        # ANSWER KEY
        # =====================================================

        gaps = answer_key.get(
            "gaps"
        )

        if not isinstance(
                gaps,
                dict,
        ):
            raise ValueError(
                "answer_key.gaps must be dict."
            )

        if set(
                gaps.keys()
        ) != set(
            gap_ids
        ):
            raise ValueError(
                "answer_key.gaps must match "
                "content gap_id values exactly."
            )

        all_accepted_answers: set[str] = set()

        for gap_id in gap_ids:
            gap_settings = gaps[
                gap_id
            ]

            if not isinstance(
                    gap_settings,
                    dict,
            ):
                raise ValueError(
                    "Each answer_key.gaps value "
                    "must be dict."
                )

            accepted_answers = (
                gap_settings.get(
                    "accepted_answers"
                )
            )

            if not isinstance(
                    accepted_answers,
                    list,
            ):
                raise ValueError(
                    "gap accepted_answers "
                    "must be list."
                )

            if not accepted_answers:
                raise ValueError(
                    "gap accepted_answers "
                    "must not be empty."
                )

            cls._validate_unique_string_list(
                accepted_answers,
                field_name=(
                    f"answer_key.gaps."
                    f"{gap_id}."
                    f"accepted_answers"
                ),
            )

            for accepted_answer in (
                    accepted_answers
            ):
                all_accepted_answers.add(
                    accepted_answer
                )

        # =====================================================
        # TEXT INPUT MODE
        # =====================================================

        if input_mode == "text_input":
            if "word_bank" in content:
                raise ValueError(
                    "content.word_bank is allowed "
                    "only for word_bank input mode."
                )

        # =====================================================
        # WORD BANK MODE
        # =====================================================

        elif input_mode == "word_bank":
            word_bank = content.get(
                "word_bank"
            )

            if not isinstance(
                    word_bank,
                    list,
            ):
                raise ValueError(
                    "content.word_bank must be list "
                    "for word_bank input mode."
                )

            if not word_bank:
                raise ValueError(
                    "content.word_bank must not "
                    "be empty."
                )

            cls._validate_unique_string_list(
                word_bank,
                field_name="content.word_bank",
            )

            word_bank_values = set(
                word_bank
            )

            missing_answers = (
                    all_accepted_answers
                    - word_bank_values
            )

            if missing_answers:
                raise ValueError(
                    "Every accepted answer must "
                    "exist in content.word_bank "
                    "for word_bank input mode."
                )

        # =====================================================
        # GRADING SETTINGS
        # =====================================================

        cls._validate_optional_bool(
            grading_settings,
            "case_sensitive",
        )

        cls._validate_optional_bool(
            grading_settings,
            "trim_whitespace",
        )

        cls._validate_optional_bool(
            grading_settings,
            "partial_credit",
        )

    # =========================================================
    # FORMULA
    # =========================================================

    @classmethod
    def _validate_formula(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        if "parts" in content or "formula_score_policy" in grading_settings:
            validate_formula_parts(content, answer_key, grading_settings, require_parts=True)
            return
        if "variables" in content:
            variables = content[
                "variables"
            ]

            if not isinstance(
                variables,
                list,
            ):
                raise ValueError(
                    "content.variables "
                    "must be list."
                )

            cls._validate_unique_string_list(
                variables,
                field_name=(
                    "content.variables"
                ),
                allow_empty=True,
            )

        cls._require_non_empty_string(
            answer_key,
            "expression",
            owner="answer_key",
        )

        if "equivalence_mode" in (
            grading_settings
        ):
            mode = (
                grading_settings[
                    "equivalence_mode"
                ]
            )

            if mode != "exact":
                raise ValueError(
                    "Only equivalence_mode='exact' "
                    "is currently supported."
                )

        validate_formula_meanings(content, answer_key, grading_settings)

    # =========================================================
    # IMAGE CHOICE
    # =========================================================

    @classmethod
    def _validate_image_choice(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        _ = grading_settings
        options = content.get("options")

        if not isinstance(options, list):
            raise ValueError(
                "content.options must be list."
            )

        if len(options) < 2:
            raise ValueError(
                "IMAGE_CHOICE requires "
                "at least 2 options."
            )

        values: list[str] = []

        for index, option in enumerate(
            options
        ):
            if not isinstance(option, dict):
                raise ValueError(
                    "Each content.options item "
                    "must be dict."
                )

            value = (
                cls._require_non_empty_string(
                    option,
                    "value",
                    owner=(
                        f"content.options[{index}]"
                    ),
                )
            )

            validate_media_segment(option)

            values.append(value)

        if len(values) != len(
            set(values)
        ):
            raise ValueError(
                "content.options values "
                "must be unique."
            )

        cls._reject_secret_fields(
            options=options,
        )

        correct_value = (
            cls._require_non_empty_string(
                answer_key,
                "value",
                owner="answer_key",
            )
        )

        if correct_value not in set(values):
            raise ValueError(
                "answer_key.value must reference "
                "an existing content option."
            )

    # =========================================================
    # MANUAL REVIEW
    # =========================================================

    @classmethod
    def _validate_manual_review(
        cls,
        *,
        content: dict[str, Any],
        answer_key: dict[str, Any],
        grading_settings: dict[str, Any],
    ) -> None:
        response_format = content.get(
            "response_format",
            "text",
        )

        if response_format not in {
            "text",
        }:
            raise ValueError(
                "Unsupported MANUAL_REVIEW "
                "response_format."
            )

        if answer_key:
            raise ValueError(
                "MANUAL_REVIEW answer_key "
                "must be empty."
            )

        manual_review = (
            grading_settings.get(
                "manual_review"
            )
        )

        if manual_review is not True:
            raise ValueError(
                "MANUAL_REVIEW requires "
                "grading_settings."
                "manual_review=True."
            )

        validate_manual_criteria(grading_settings.get("criteria"))

    # =========================================================
    # COMMON HELPERS
    # =========================================================
    @classmethod
    def _validate_rich_content_segments(
            cls,
            segments: Any,
            *,
            field_name: str,
    ) -> list[dict[str, Any]]:
        """
        Проверяет отображаемый rich-content.

        Для text_segments условия также допускается image:
        object_key — постоянный ключ media, alt — описание.
        Варианты ответа сохраняют прежние правила text / latex.

        Поддерживаемые сегменты:

            text
                Обычный текст.

            latex
                Математическое выражение
                в формате LaTeX.

        Пример:

            [
                {
                    "type": "text",
                    "text": "x мәні ",
                },
                {
                    "type": "latex",
                    "text": r"\\frac{1}{2}",
                },
                {
                    "type": "text",
                    "text": "-ге тең",
                },
            ]
        """

        if not isinstance(segments, list):
            raise ValueError(
                f"{field_name} must be list."
            )

        if not segments:
            raise ValueError(
                f"{field_name} must not be empty."
            )

        for index, segment in enumerate(
                segments
        ):
            if not isinstance(segment, dict):
                raise ValueError(
                    f"Each {field_name} item "
                    "must be dict."
                )

            owner = (
                f"{field_name}[{index}]"
            )

            segment_type = (
                cls._require_non_empty_string(
                    segment,
                    "type",
                    owner=owner,
                )
            )

            if segment_type == "image" and field_name == "text_segments":
                object_key = cls._require_non_empty_string(
                    segment,
                    "object_key",
                    owner=owner,
                )
                if not re.fullmatch(
                    r"question-bank/media/[1-9][0-9]*/[0-9a-f]{32}\.(?:png|jpg|webp)",
                    object_key,
                ):
                    raise ValueError(f"{owner}.object_key is invalid.")

                alt = segment.get("alt", "")
                if not isinstance(alt, str) or len(alt) > 500:
                    raise ValueError(
                        f"{owner}.alt must be string, at most 500 characters."
                    )
                continue

            if segment_type not in {
                "text",
                "latex",
            }:
                raise ValueError(
                    f"{owner}.type must be "
                    + ("'text', 'latex' or 'image'." if field_name == "text_segments"
                       else "'text' or 'latex'.")
                )

            cls._require_non_empty_string(
                segment,
                "text",
                owner=owner,
            )

        return segments

    @classmethod
    def _validate_options(
        cls,
        *,
        content: dict[str, Any],
        minimum: int,
    ) -> list[dict[str, Any]]:
        return cls._validate_named_items(
            content.get("options"),
            field_name="content.options",
            minimum=minimum,
        )

    @classmethod
    def _validate_named_items(
            cls,
            items: Any,
            *,
            field_name: str,
            minimum: int,
    ) -> list[dict[str, Any]]:
        if not isinstance(
                items,
                list,
        ):
            raise ValueError(
                f"{field_name} must be list."
            )

        if len(items) < minimum:
            raise ValueError(
                f"{field_name} requires "
                f"at least {minimum} items."
            )

        values: list[str] = []

        for index, item in enumerate(
                items
        ):
            if not isinstance(
                    item,
                    dict,
            ):
                raise ValueError(
                    f"Each {field_name} item "
                    "must be dict."
                )

            owner = (
                f"{field_name}[{index}]"
            )

            value = (
                cls._require_non_empty_string(
                    item,
                    "value",
                    owner=owner,
                )
            )

            cls._validate_rich_content_segments(
                item.get("segments"),
                field_name=(
                    f"{owner}.segments"
                ),
            )

            values.append(
                value
            )

        if len(values) != len(
                set(values)
        ):
            raise ValueError(
                f"{field_name} values "
                f"must be unique."
            )

        return items

    @staticmethod
    def _reject_secret_fields(
        *,
        options: list[dict[str, Any]],
    ) -> None:
        """
        Защита от утечки правильного ответа
        в student-visible content.
        """

        forbidden_fields = {
            "is_correct",
            "correct",
            "score",
        }

        for option in options:
            leaked_fields = (
                forbidden_fields
                & set(option.keys())
            )

            if leaked_fields:
                leaked = ", ".join(
                    sorted(leaked_fields)
                )

                raise ValueError(
                    "Student-visible content "
                    "contains forbidden secret "
                    f"field(s): {leaked}."
                )

    @staticmethod
    def _require_non_empty_string(
        mapping: Mapping[str, Any],
        key: str,
        *,
        owner: str,
    ) -> str:
        value = mapping.get(key)

        if not isinstance(value, str):
            raise ValueError(
                f"{owner}.{key} "
                "must be string."
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                f"{owner}.{key} "
                "must not be empty."
            )

        return normalized

    @staticmethod
    def _validate_unique_string_list(
        values: list[Any],
        *,
        field_name: str,
        allow_empty: bool = False,
    ) -> None:
        if (
            not allow_empty
            and not values
        ):
            raise ValueError(
                f"{field_name} "
                "must not be empty."
            )

        normalized_values: list[str] = []

        for value in values:
            if not isinstance(value, str):
                raise ValueError(
                    f"{field_name} values "
                    "must be strings."
                )

            normalized = value.strip()

            if not normalized:
                raise ValueError(
                    f"{field_name} values "
                    "must not be empty."
                )

            normalized_values.append(
                normalized
            )

        if len(normalized_values) != len(
            set(normalized_values)
        ):
            raise ValueError(
                f"{field_name} values "
                "must be unique."
            )

    @staticmethod
    def _validate_optional_bool(
        mapping: Mapping[str, Any],
        key: str,
    ) -> None:
        if key not in mapping:
            return

        if type(mapping[key]) is not bool:
            raise ValueError(
                f"{key} must be bool."
            )

    @staticmethod
    def _validate_real_number(
        value: Any,
        *,
        field_name: str,
    ) -> None:
        # bool является подклассом int,
        # поэтому отклоняем его явно.
        if (
            type(value) is bool
            or not isinstance(value, Real)
        ):
            raise ValueError(
                f"{field_name} "
                "must be a real number."
            )
