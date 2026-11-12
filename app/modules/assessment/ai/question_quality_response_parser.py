# app/modules/assessment/ai/question_quality_response_parser.py
from __future__ import annotations

import json
from typing import Any

from app.modules.assessment.enums import (
    AIQuestionQualityIssueSeverity,
    AIQuestionQualityVerdict,
)
from app.modules.assessment.schemas.ai_question_quality_review_dto import (
    AIQuestionQualityReviewIssueDTO,
    AIQuestionQualityReviewResultDTO,
)


class AIQuestionQualityResponseParser:
    """
    Преобразует недоверенный structured response AI
    в внутренний DTO результата Quality Review.

    Parser проверяет:
    - JSON;
    - верхнеуровневую структуру;
    - verdict;
    - summary;
    - issues;
    - issue.code;
    - issue.severity;
    - issue.message;
    - issue.suggestion;
    - логическую согласованность verdict и issues.

    Parser НЕ определяет самостоятельно качество вопроса.

    Он только проверяет, что AI вернул корректный
    и непротиворечивый structured response.
    """

    @classmethod
    def parse_json(
        cls,
        *,
        raw_json: str,
    ) -> AIQuestionQualityReviewResultDTO:
        if not isinstance(raw_json, str):
            raise ValueError(
                "AI quality review response "
                "должен быть строкой JSON."
            )

        if not raw_json.strip():
            raise ValueError(
                "AI quality review response "
                "не должен быть пустым."
            )

        try:
            payload = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "AI quality review вернул "
                "некорректный JSON."
            ) from exc

        return cls.parse_payload(
            payload=payload,
        )

    @classmethod
    def parse_payload(
        cls,
        *,
        payload: Any,
    ) -> AIQuestionQualityReviewResultDTO:
        if not isinstance(payload, dict):
            raise ValueError(
                "Корень AI quality review response "
                "должен быть object."
            )

        verdict = cls._parse_verdict(
            payload.get("verdict")
        )

        summary = cls._require_non_empty_string(
            payload.get("summary"),
            field="summary",
        )

        issues = cls._parse_issues(
            payload.get("issues", [])
        )

        cls._validate_verdict_consistency(
            verdict=verdict,
            issues=issues,
        )

        return AIQuestionQualityReviewResultDTO(
            verdict=verdict,
            summary=summary,
            issues=issues,
            # Provider metadata приходит не от модели.
            metadata={},
        )

    # ============================================================
    # VERDICT
    # ============================================================

    @staticmethod
    def _parse_verdict(
        value: Any,
    ) -> AIQuestionQualityVerdict:
        if not isinstance(value, str):
            raise ValueError(
                "verdict должен быть string."
            )

        try:
            return AIQuestionQualityVerdict(value)
        except ValueError as exc:
            raise ValueError(
                "verdict содержит неизвестное значение: "
                f"{value!r}."
            ) from exc

    # ============================================================
    # ISSUES
    # ============================================================

    @classmethod
    def _parse_issues(
        cls,
        value: Any,
    ) -> tuple[AIQuestionQualityReviewIssueDTO, ...]:
        if not isinstance(value, list):
            raise ValueError(
                "issues должен быть list."
            )

        result: list[
            AIQuestionQualityReviewIssueDTO
        ] = []

        seen_codes: set[str] = set()

        for index, raw_issue in enumerate(
            value,
            start=1,
        ):
            issue = cls._parse_issue(
                raw_issue=raw_issue,
                index=index,
            )

            if issue.code in seen_codes:
                raise ValueError(
                    "issues содержит duplicate code: "
                    f"{issue.code!r}."
                )

            seen_codes.add(issue.code)
            result.append(issue)

        return tuple(result)

    @classmethod
    def _parse_issue(
        cls,
        *,
        raw_issue: Any,
        index: int,
    ) -> AIQuestionQualityReviewIssueDTO:
        prefix = f"issues[{index}]"

        if not isinstance(raw_issue, dict):
            raise ValueError(
                f"{prefix} должен быть object."
            )

        code = cls._require_non_empty_string(
            raw_issue.get("code"),
            field=f"{prefix}.code",
        )

        severity = cls._parse_severity(
            raw_issue.get("severity"),
            field=f"{prefix}.severity",
        )

        message = cls._require_non_empty_string(
            raw_issue.get("message"),
            field=f"{prefix}.message",
        )

        suggestion = cls._optional_string(
            raw_issue.get("suggestion"),
            field=f"{prefix}.suggestion",
        )

        return AIQuestionQualityReviewIssueDTO(
            code=code,
            severity=severity,
            message=message,
            suggestion=suggestion,
        )

    # ============================================================
    # SEVERITY
    # ============================================================

    @staticmethod
    def _parse_severity(
        value: Any,
        *,
        field: str,
    ) -> AIQuestionQualityIssueSeverity:
        if not isinstance(value, str):
            raise ValueError(
                f"{field} должен быть string."
            )

        try:
            return AIQuestionQualityIssueSeverity(value)
        except ValueError as exc:
            raise ValueError(
                f"{field} содержит неизвестное "
                f"значение: {value!r}."
            ) from exc

    # ============================================================
    # VERDICT CONSISTENCY
    # ============================================================

    @staticmethod
    def _validate_verdict_consistency(
        *,
        verdict: AIQuestionQualityVerdict,
        issues: tuple[
            AIQuestionQualityReviewIssueDTO,
            ...
        ],
    ) -> None:
        """
        Проверяет логическую согласованность verdict
        и списка issues.

        PASS:
            ERROR issues недопустимы.

        NEEDS_REVIEW:
            должен существовать хотя бы один issue.

        REJECT:
            должен существовать хотя бы один ERROR.

        WARNING при PASS допустим:
            AI может считать вопрос в целом пригодным,
            но оставить некритическое замечание
            для человека.
        """

        error_count = sum(
            1
            for issue in issues
            if (
                issue.severity
                == AIQuestionQualityIssueSeverity.ERROR
            )
        )

        if (
            verdict == AIQuestionQualityVerdict.PASS
            and error_count > 0
        ):
            raise ValueError(
                "verdict=pass несовместим "
                "с issue severity=error."
            )

        if (
            verdict
            == AIQuestionQualityVerdict.NEEDS_REVIEW
            and not issues
        ):
            raise ValueError(
                "verdict=needs_review требует "
                "хотя бы один issue."
            )

        if (
            verdict == AIQuestionQualityVerdict.REJECT
            and error_count == 0
        ):
            raise ValueError(
                "verdict=reject требует "
                "хотя бы один issue "
                "severity=error."
            )

    # ============================================================
    # SCALAR HELPERS
    # ============================================================

    @staticmethod
    def _require_non_empty_string(
        value: Any,
        *,
        field: str,
    ) -> str:
        if not isinstance(value, str):
            raise ValueError(
                f"{field} должен быть string."
            )

        value = value.strip()

        if not value:
            raise ValueError(
                f"{field} не должен быть пустым."
            )

        return value

    @staticmethod
    def _optional_string(
        value: Any,
        *,
        field: str,
    ) -> str | None:
        if value is None:
            return None

        if not isinstance(value, str):
            raise ValueError(
                f"{field} должен быть string или null."
            )

        value = value.strip()

        return value or None
