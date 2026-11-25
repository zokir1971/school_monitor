"""Bounded annual-plan PDF rendering with no ORM objects in the worker process."""
from dataclasses import dataclass

import anyio
from anyio.lowlevel import RunVar
from anyio import to_process


@dataclass(frozen=True, slots=True)
class PdfPlan:
    id: int
    academic_year: str


@dataclass(frozen=True, slots=True)
class PdfDirection:
    short_title: str
    full_title: str | None


@dataclass(frozen=True, slots=True)
class PdfRow4:
    control_object: str | None
    risk_text: str | None
    decision_text: str | None


@dataclass(frozen=True, slots=True)
class PdfRow11:
    topic: str | None
    goal: str | None
    control_object: str | None
    control_type: str | None
    methods: str | None
    period_text: str | None
    responsibles_text: str | None
    review_places_text: str | None
    documents_text: str | None
    second_control: str | None


@dataclass(frozen=True, slots=True)
class PdfBlock:
    direction: PdfDirection
    rows4: tuple[PdfRow4, ...]
    rows11: tuple[PdfRow11, ...]


@dataclass(frozen=True, slots=True)
class PdfDocument:
    plan: PdfPlan
    directions: tuple[PdfBlock, ...]
    language: str = "kk"


def snapshot_plan_pdf(dto):
    """Copy only scalar fields used by PlanVshkPdf, before closing the session."""
    blocks = []
    for block in dto.directions:
        rows4 = tuple(PdfRow4(row.control_object, row.risk_text, row.decision_text)
                      for row in block.rows4)
        rows11 = tuple(PdfRow11(**{name: getattr(row, name)
                                  for name in PdfRow11.__dataclass_fields__})
                       for row in block.rows11)
        blocks.append(PdfBlock(PdfDirection(block.direction.short_title,
                                             block.direction.full_title), rows4, rows11))
    from app.modules.planning.content_i18n import language
    return PdfDocument(PdfPlan(dto.plan.id, dto.plan.academic_year), tuple(blocks), language())


class PdfWorkerUnavailable(Exception):
    """The isolated PDF worker could not complete its request."""


class PdfQueueBusy(Exception):
    """The small per-process annual PDF queue is full."""


@dataclass
class _WorkerState:
    limiter: anyio.CapacityLimiter
    pending: int = 0


_state = RunVar("school_monitor_annual_pdf_worker")
MAX_PENDING = 8  # Includes the active PDF; waiting requests keep no DB connection.


def _get_state():
    try:
        return _state.get()
    except LookupError:
        state = _WorkerState(anyio.CapacityLimiter(1))
        _state.set(state)
        return state


def _build_sync(document, meta):
    from app.utils.plan_vshk_pdf import PlanVshkPdf
    return PlanVshkPdf.build(document, meta=meta)


async def build_plan_pdf(document, *, meta):
    state = _get_state()
    if state.pending >= MAX_PENDING:
        raise PdfQueueBusy
    state.pending += 1
    try:
        return await to_process.run_sync(
            _build_sync, document, meta, limiter=state.limiter,
            cancellable=False,
        )
    except anyio.BrokenWorkerProcess as exc:
        raise PdfWorkerUnavailable from exc
    finally:
        state.pending -= 1
