# app/modules/reports/services/report_template_resolver.py

from __future__ import annotations

from app.modules.reports.assessment_report_types import REPORT_TYPES

from copy import deepcopy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reports.enums import (
    ReportTemplateMode,
    ReportType,
)
from app.modules.reports.repositories.user_template_repo import (
    UserReportTemplateRepo,
)
from app.modules.reports.schemas.report_template_dto import (
    ResolvedReportTemplateDTO,
)
from app.modules.reports.system_schemas.checking_notebooks_schemas import (
    CHECKING_NOTEBOOKS_SYSTEM_SCHEMA,
)
from app.modules.reports.system_schemas.lesson_observation_schema import (
    LESSON_OBSERVATION_SCHEMA,
)


class ReportTemplateResolver:
    """
    Единая точка определения структуры шаблона отчета.

    Resolver отвечает только за выбор источника schema:
    - STANDARD -> встроенная системная схема;
    - CUSTOM   -> UserReportTemplate.schema_json.

    Он НЕ:
    - создает TaskExecutionDocument;
    - применяет шаблон к задаче;
    - делает commit;
    - сохраняет черновик;
    - подписывает отчет.

    Поэтому resolver безопасно использовать в GET /fill:
    открытие формы не изменяет состояние БД.
    """

    _SYSTEM_SCHEMAS: dict[str, dict[str, Any]] = {
        ReportType.CHECKING_NOTEBOOKS_TABLE.value:
            CHECKING_NOTEBOOKS_SYSTEM_SCHEMA,

        ReportType.LESSON_OBSERVATION.value:
            LESSON_OBSERVATION_SCHEMA,
    }

    # =========================================================
    # PUBLIC API
    # =========================================================

    @classmethod
    async def resolve(
            cls,
            db: AsyncSession,
            *,
            report_code: str,
            template_mode: ReportTemplateMode | str,
            owner_user_id: int,
            template_id: int | None = None,
    ) -> ResolvedReportTemplateDTO:
        """
        Разрешить шаблон отчета в единый DTO.

        Для STANDARD template_id не нужен.
        Для CUSTOM template_id обязателен и шаблон должен:
        - существовать;
        - быть активным;
        - принадлежать owner_user_id;
        - соответствовать report_code.
        """

        normalized_code = cls._normalize_report_code(
            report_code
        )

        normalized_mode = cls._normalize_template_mode(
            template_mode
        )

        if normalized_mode == ReportTemplateMode.STANDARD:
            return cls._resolve_system(
                report_code=normalized_code,
            )

        if normalized_mode == ReportTemplateMode.CUSTOM:
            if normalized_code in REPORT_TYPES:
                raise ValueError("Для этого отчёта доступен только системный шаблон. / Бұл есеп үшін тек жүйелік үлгі қолжетімді.")
            return await cls._resolve_user(
                db,
                report_code=normalized_code,
                owner_user_id=owner_user_id,
                template_id=template_id,
            )

        # Формально сюда попасть нельзя после _normalize_template_mode,
        # но оставляем защиту на случай изменения enum.
        raise ValueError(
            "Неподдерживаемый режим шаблона отчета."
        )

    # =========================================================
    # SYSTEM
    # =========================================================

    @classmethod
    def _resolve_system(
            cls,
            *,
            report_code: str,
    ) -> ResolvedReportTemplateDTO:
        schema = cls._SYSTEM_SCHEMAS.get(
            report_code
        )

        if not schema:
            raise ValueError(
                "Для данного типа отчета системный шаблон не настроен."
            )

        report_type = cls._get_report_type(
            report_code
        )

        return ResolvedReportTemplateDTO(
            report_code=report_type.value,
            report_label=report_type.label_kz,
            template_mode=ReportTemplateMode.STANDARD,

            # Возвращаем независимую копию.
            # Сервис заполнения может нормализовать schema,
            # не изменяя глобальную системную константу.
            schema=deepcopy(schema),

            user_template_id=None,
            template_title=report_type.label_kz,
        )

    # =========================================================
    # USER
    # =========================================================

    @classmethod
    async def _resolve_user(
            cls,
            db: AsyncSession,
            *,
            report_code: str,
            owner_user_id: int,
            template_id: int | None,
    ) -> ResolvedReportTemplateDTO:
        if template_id is None:
            raise ValueError(
                "Не выбран пользовательский шаблон отчета."
            )

        template = await UserReportTemplateRepo.get_user_template(
            db,
            template_id=template_id,
            owner_user_id=owner_user_id,
        )

        if template is None:
            raise ValueError(
                "Пользовательский шаблон не найден или недоступен."
            )

        if template.report_code != report_code:
            raise ValueError(
                "Пользовательский шаблон не соответствует выбранному типу отчета."
            )

        schema = template.schema_json or {}

        if not schema:
            raise ValueError(
                "В пользовательском шаблоне отсутствует структура отчета."
            )

        report_type = cls._get_report_type(
            report_code
        )

        return ResolvedReportTemplateDTO(
            report_code=report_code,
            report_label=(
                template.report_label
                or report_type.label_kz
            ),
            template_mode=ReportTemplateMode.CUSTOM,
            schema=deepcopy(schema),
            user_template_id=template.id,
            template_title=template.title,
        )

    # =========================================================
    # NORMALIZATION
    # =========================================================

    @staticmethod
    def _normalize_template_mode(
            template_mode: ReportTemplateMode | str,
    ) -> ReportTemplateMode:
        if isinstance(
                template_mode,
                ReportTemplateMode,
        ):
            return template_mode

        raw_value = str(
            template_mode or ""
        ).strip()

        # Поддерживаем пользовательскую терминологию system/user
        # только на входной границе. Внутри новой архитектуры
        # используем существующий enum STANDARD/CUSTOM.
        aliases = {
            "system": ReportTemplateMode.STANDARD,
            "standard": ReportTemplateMode.STANDARD,

            "user": ReportTemplateMode.CUSTOM,
            "custom": ReportTemplateMode.CUSTOM,
        }

        normalized = aliases.get(
            raw_value.lower()
        )

        if normalized is None:
            raise ValueError(
                "Некорректный режим шаблона отчета."
            )

        return normalized

    @staticmethod
    def _normalize_report_code(
            report_code: str,
    ) -> str:
        value = str(
            report_code or ""
        ).strip()

        if not value:
            raise ValueError(
                "Не указан тип отчета."
            )

        return value

    @staticmethod
    def _get_report_type(
            report_code: str,
    ) -> ReportType:
        try:
            return ReportType(
                report_code
            )
        except ValueError as exc:
            raise ValueError(
                f"Неизвестный тип отчета: {report_code}"
            ) from exc
