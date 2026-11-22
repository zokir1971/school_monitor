"""Read current template hints without modifying school data."""
from sqlalchemy import select
from app.modules.planning.models import PlanTemplateDirection, PlanTemplateRow11

SAMPLE_FIELDS = ('deadlines', 'responsibles', 'review_place', 'management_decision')


async def load_direction_samples(db, *, template_id, direction_id, rows):
    # Existing plans use template + direction + order, never primary-key equality.
    eligible = [r for r in rows if not r.is_custom and r.direction_id == direction_id]
    orders = {r.row_order for r in eligible}
    if not orders:
        return {}
    t = PlanTemplateRow11.__table__
    td = PlanTemplateDirection.__table__
    result = await db.execute(
        select(t.c.id, t.c.row_order, *(t.c[name] for name in SAMPLE_FIELDS))
        .join(td, td.c.id == t.c.template_direction_id)
        .where(td.c.template_id == template_id,
               td.c.direction_id == direction_id,
               t.c.row_order.in_(orders))
    )
    by_order = {r['row_order']: dict(r) for r in result.mappings()}
    return {r.id: by_order[r.row_order] for r in eligible if r.row_order in by_order}
