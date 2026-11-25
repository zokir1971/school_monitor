from __future__ import annotations
from app.modules.planning.content_i18n import content_text, display_view, language
from app.core.i18n import translate

from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app.modules.org.models import School, District
from app.modules.planning.enums import (
    ResponsibleRole,
    AssignmentKind,
    PlanPeriodType,
    ReviewPlace,
)
from app.modules.reports.enums import DocumentType
from app.modules.planning.models_school import (
    SchoolPlan,
    SchoolPlanRow4,
    SchoolPlanRow11,
    SchoolPlanRow11Responsible,
    SchoolPlanRow11ReviewPlace,
    SchoolPlanRow11RequiredDocument,
)
from app.modules.users.models import User


@dataclass
class PlanMeta:
    school_name: str
    director_fio: str
    district_name: str | None = None


@dataclass
class ExportResponsibleDTO:
    value: str
    label: str
    assignment_kind: str | None = None
    assignment_kind_label: str | None = None


@dataclass
class ExportReviewPlaceDTO:
    value: str
    label: str


@dataclass
class ExportDocumentDTO:
    value: str
    label: str


@dataclass
class ExportRow11DTO:
    id: int
    row_order: int

    topic: str | None
    goal: str | None
    control_object: str | None
    control_type: str | None
    methods: str | None
    second_control: str | None

    period_type: str | None
    period_type_label: str | None
    period_type_int: int | None
    period_type_values: list[int]
    period_text: str

    responsibles: list[ExportResponsibleDTO] = field(default_factory=list)
    review_places: list[ExportReviewPlaceDTO] = field(default_factory=list)
    documents: list[ExportDocumentDTO] = field(default_factory=list)

    responsibles_text: str = ""
    review_places_text: str = ""
    documents_text: str = ""


@dataclass
class DirectionBlock:
    direction: object
    rows4: list[SchoolPlanRow4]
    rows11: list[ExportRow11DTO]


@dataclass
class FullPlanDTO:
    plan: SchoolPlan
    directions: list[DirectionBlock]
    meta: PlanMeta


class SchoolPlanExportService:
    MONTH_NAMES = {
        1: "Қаңтар",
        2: "Ақпан",
        3: "Наурыз",
        4: "Сәуір",
        5: "Мамыр",
        6: "Маусым",
        7: "Шілде",
        8: "Тамыз",
        9: "Қыркүйек",
        10: "Қазан",
        11: "Қараша",
        12: "Желтоқсан",
    }

    @staticmethod
    def _enum_value(v) -> str:
        if v is None:
            return ""
        return getattr(v, "value", str(v))

    @staticmethod
    def _enum_label(enum_cls, raw_value: str) -> str:
        if not raw_value:
            return ""
        try:
            return translate(enum_cls(raw_value).label_kz, language())
        except (ValueError, TypeError):
            return raw_value

    @classmethod
    def _month_name(cls, month_num: int | None) -> str:
        if not month_num:
            return ""
        return translate(cls.MONTH_NAMES.get(month_num, str(month_num)), language())

    @classmethod
    def _normalize_period_values(cls, raw_values) -> list[int]:
        if not raw_values:
            return []

        if isinstance(raw_values, list):
            result: list[int] = []
            for x in raw_values:
                try:
                    result.append(int(x))
                except (TypeError, ValueError):
                    pass
            return result

        if isinstance(raw_values, str):
            result: list[int] = []
            for x in raw_values.split(","):
                x = x.strip()
                if x.isdigit():
                    result.append(int(x))
            return result

        return []

    @classmethod
    def _build_period_text(cls, row: SchoolPlanRow11) -> str:
        period_type = cls._enum_value(getattr(row, "period_type", None))

        period_type_int = getattr(row, "period_type_int", None)
        if period_type_int is None:
            period_type_int = getattr(row, "period_value_int", None)

        raw_period_values = getattr(row, "period_type_values", None)
        if raw_period_values is None:
            raw_period_values = getattr(row, "period_values", None)

        period_type_values = cls._normalize_period_values(raw_period_values)

        if period_type == PlanPeriodType.MONTH.value:
            return cls._month_name(period_type_int)

        if period_type == PlanPeriodType.MONTHS.value:
            months = [cls._month_name(x) for x in period_type_values if x]
            return ", ".join([m for m in months if m])

        if period_type == PlanPeriodType.MONTHLY.value:
            return translate(PlanPeriodType.MONTHLY.label_kz, language())

        if period_type == PlanPeriodType.QUARTER.value:
            return translate(PlanPeriodType.QUARTER.label_kz, language())

        if period_type == PlanPeriodType.ALL_YEAR.value:
            return translate(PlanPeriodType.ALL_YEAR.label_kz, language())

        return ""

    @staticmethod
    def _join_responsibles(items: list[ExportResponsibleDTO]) -> str:
        parts: list[str] = []

        for item in items or []:
            label = (item.label or "").strip()
            kind_label = (item.assignment_kind_label or "").strip()

            if not label:
                continue

            if kind_label:
                parts.append(f"{label} ({kind_label})")
            else:
                parts.append(label)

        return ", ".join(parts)

    @staticmethod
    def _join_review_places(items: list[ExportReviewPlaceDTO]) -> str:
        return ", ".join(
            item.label.strip()
            for item in (items or [])
            if item and item.label and item.label.strip()
        )

    @staticmethod
    def _join_documents(items: list[ExportDocumentDTO]) -> str:
        return ", ".join(
            item.label.strip()
            for item in (items or [])
            if item and item.label and item.label.strip()
        )

    @staticmethod
    def _group_by_row11_id(items: list) -> dict[int, list]:
        result: dict[int, list] = defaultdict(list)
        for item in items:
            result[item.row11_id].append(item)
        return result

    @classmethod
    def _build_row11_dto(
            cls,
            row: SchoolPlanRow11,
            *,
            responsibles_items: list | None = None,
            review_place_items: list | None = None,
            document_items: list | None = None,
    ) -> ExportRow11DTO:
        period_type_value = cls._enum_value(getattr(row, "period_type", None))
        period_type_values = cls._normalize_period_values(
            getattr(row, "period_type_values", None)
        )

        responsibles: list[ExportResponsibleDTO] = []
        for item in (responsibles_items or []):
            role_raw = cls._enum_value(getattr(item, "role", None))
            kind_raw = cls._enum_value(getattr(item, "assignment_kind", None))

            if not role_raw:
                continue

            responsibles.append(
                ExportResponsibleDTO(
                    value=role_raw,
                    label=cls._enum_label(ResponsibleRole, role_raw),
                    assignment_kind=kind_raw or None,
                    assignment_kind_label=(
                        cls._enum_label(AssignmentKind, kind_raw) if kind_raw else None
                    ),
                )
            )

        review_places: list[ExportReviewPlaceDTO] = []
        for item in (review_place_items or []):
            raw = cls._enum_value(getattr(item, "review_place", None))
            if not raw:
                continue

            review_places.append(
                ExportReviewPlaceDTO(
                    value=raw,
                    label=cls._enum_label(ReviewPlace, raw),
                )
            )

        documents: list[ExportDocumentDTO] = []
        for item in (document_items or []):
            raw = cls._enum_value(getattr(item, "document_type", None))
            if not raw:
                continue

            documents.append(
                ExportDocumentDTO(
                    value=raw,
                    label=cls._enum_label(DocumentType, raw),
                )
            )
        responsibles_text = cls._join_responsibles(responsibles)
        review_places_text = cls._join_review_places(review_places)
        documents_text = cls._join_documents(documents)

        return ExportRow11DTO(
            id=row.id,
            row_order=row.row_order,
            topic=content_text(row, "topic"),
            goal=content_text(row, "goal"),
            control_object=content_text(row, "control_object"),
            control_type=content_text(row, "control_type"),
            methods=content_text(row, "methods"),

            period_type=period_type_value or None,
            period_type_label=(
                cls._enum_label(PlanPeriodType, period_type_value)
                if period_type_value else None
            ),
            period_type_int=getattr(row, "period_type_int", None),
            period_type_values=period_type_values,
            period_text=cls._build_period_text(row),

            responsibles=responsibles,
            review_places=review_places,
            documents=documents,

            responsibles_text=responsibles_text,
            review_places_text=review_places_text,
            documents_text=documents_text,
            second_control=content_text(row, "second_control")
        )

    @staticmethod
    async def get_full_plan(
            db: AsyncSession,
            *,
            school_plan_id: int,
            user: User,
    ) -> FullPlanDTO | None:
        if user.school_id is None:
            return None

        # Scope the root query before any export rows are read. Disable default
        # relationship loading only for these queries; DTO content stays the same.
        plan: SchoolPlan | None = await db.scalar(
            select(SchoolPlan)
            .where(SchoolPlan.id == school_plan_id, SchoolPlan.school_id == user.school_id)
            .options(raiseload("*"))
        )
        if plan is None or plan.school_id != user.school_id:
            return None

        school: School | None = await db.get(School, user.school_id, options=[raiseload("*")])
        if school is None:
            return None

        district: District | None = None
        if school.district_id:
            district = await db.get(District, school.district_id, options=[raiseload("*")])

        meta = PlanMeta(
            school_name=(school.name or "").strip() or f"Школа #{school.id}",
            director_fio=(user.full_name or "").strip() or "________________________",
            district_name=(district.name if district else None),
        )

        from app.modules.planning.models import PlanDirection

        directions = list((await db.scalars(
            select(PlanDirection).options(raiseload("*"))
            .order_by(PlanDirection.sort_order.asc(), PlanDirection.id.asc())
        )).all())

        # Read each table once for the entire plan. Query count is independent
        # of the number of directions and rows, with no large IN parameter list.
        rows4_all = list((await db.scalars(
            select(SchoolPlanRow4).options(raiseload("*"))
            .where(SchoolPlanRow4.school_plan_id == school_plan_id, SchoolPlanRow4.is_excluded.is_(False))
            .order_by(SchoolPlanRow4.row_order.asc(), SchoolPlanRow4.id.asc())
        )).all())
        rows11_all = list((await db.scalars(
            select(SchoolPlanRow11).options(raiseload("*"))
            .where(SchoolPlanRow11.school_plan_id == school_plan_id, SchoolPlanRow11.is_excluded.is_(False))
            .order_by(SchoolPlanRow11.row_order.asc(), SchoolPlanRow11.id.asc())
        )).all())

        rows4_by_direction: dict[int, list] = defaultdict(list)
        rows11_by_direction: dict[int, list] = defaultdict(list)
        for row in rows4_all:
            rows4_by_direction[row.direction_id].append(row)
        for row in rows11_all:
            rows11_by_direction[row.direction_id].append(row)

        async def children_for_plan(model):
            return list((await db.scalars(
                select(model).options(raiseload("*"))
                .join(SchoolPlanRow11, model.row11_id == SchoolPlanRow11.id)
                .where(SchoolPlanRow11.school_plan_id == school_plan_id, SchoolPlanRow11.is_excluded.is_(False))
                .order_by(model.row11_id.asc(), model.id.asc())
            )).all())

        responsibles_map: dict[int, list] = {}
        review_places_map: dict[int, list] = {}
        documents_map: dict[int, list] = {}
        if rows11_all:
            responsibles_map = SchoolPlanExportService._group_by_row11_id(
                await children_for_plan(SchoolPlanRow11Responsible)
            )
            review_places_map = SchoolPlanExportService._group_by_row11_id(
                await children_for_plan(SchoolPlanRow11ReviewPlace)
            )
            documents_map = SchoolPlanExportService._group_by_row11_id(
                await children_for_plan(SchoolPlanRow11RequiredDocument)
            )

        blocks: list[DirectionBlock] = []
        for direction in directions:
            rows4 = rows4_by_direction.get(direction.id, [])
            rows11 = [
                SchoolPlanExportService._build_row11_dto(
                    row,
                    responsibles_items=responsibles_map.get(row.id, []),
                    review_place_items=review_places_map.get(row.id, []),
                    document_items=documents_map.get(row.id, []),
                )
                for row in rows11_by_direction.get(direction.id, [])
            ]
            if rows4 or rows11:
                blocks.append(DirectionBlock(direction=display_view(direction), rows4=display_view(rows4), rows11=rows11))

        return FullPlanDTO(plan=plan, directions=blocks, meta=meta)
