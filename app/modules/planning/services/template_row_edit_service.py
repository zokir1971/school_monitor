"""Scoped template edits; existing school plans are never updated here."""
import hashlib
import json
from fastapi import HTTPException
from sqlalchemy import select, update
from app.modules.planning.models import PlanTemplateRow4, PlanTemplateRow11, PlanTemplateDirection, PlanTemplate, PlanDirection
from app.modules.planning.enums import ReviewPlace
from app.modules.planning.repositories.review_place_sync_repo import ReviewPlaceSyncRepo

FIELDS = {
    'rows4': ('control_object', 'risk_text', 'decision_text'),
    'rows11': ('topic', 'goal', 'control_object', 'control_type', 'methods', 'deadlines', 'responsibles', 'review_place', 'management_decision', 'second_control'),
}
MODELS = {'rows4': PlanTemplateRow4, 'rows11': PlanTemplateRow11}


class TemplateRowEditService:
    @staticmethod
    async def load(db, *, kind, row_id, template_id, direction_id, lock=False):
        if kind not in MODELS:
            raise HTTPException(404, 'Строка не найдена / Жол табылмады')
        r, td = MODELS[kind].__table__, PlanTemplateDirection.__table__
        t, d = PlanTemplate.__table__, PlanDirection.__table__
        stmt = select(r, t.c.name.label('template_name'), d.c.short_title.label('direction_name')).join(td, td.c.id == r.c.template_direction_id).join(t, t.c.id == td.c.template_id).join(d, d.c.id == td.c.direction_id).where(r.c.id == row_id, td.c.template_id == template_id, td.c.direction_id == direction_id)
        if lock:
            stmt = stmt.with_for_update(of=r)
        row = (await db.execute(stmt)).mappings().first()
        if row is None:
            raise HTTPException(404, 'Строка не найдена в выбранном шаблоне и направлении / Таңдалған үлгі мен бағытта жол табылмады')
        return dict(row)

    @staticmethod
    def revision(kind, row):
        values = {k: row[k] for k in ('id', 'template_direction_id', 'row_order', *FIELDS[kind])}
        return hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def review_value(row):
        raw = row.get('review_place') or ''
        parsed = ReviewPlaceSyncRepo.legacy_places(raw)
        return next(iter(parsed)) if parsed and len(parsed) == 1 else raw

    @classmethod
    async def save(cls, db, *, kind, row_id, template_id, direction_id, revision, form):
        row = await cls.load(db, kind=kind, row_id=row_id, template_id=template_id, direction_id=direction_id, lock=True)
        if revision != cls.revision(kind, row):
            raise HTTPException(409, 'Строка уже изменена. Откройте её заново / Жол өзгертілген. Оны қайта ашыңыз')
        values = {}
        for name in FIELDS[kind]:
            submitted = form.getlist(name)
            if len(submitted) != 1 or not isinstance(submitted[0], str):
                raise HTTPException(400, 'Форма неполная. Откройте строку заново / Нысан толық емес. Жолды қайта ашыңыз')
            value = submitted[0].strip()
            if len(value) > 50000:
                raise HTTPException(400, 'Слишком длинное значение поля / Өріс мәні тым ұзын')
            values[name] = value or None
        required = 'topic' if kind == 'rows11' else 'control_object'
        if not values[required]:
            raise HTTPException(400, 'Заполните обязательное поле / Міндетті өрісті толтырыңыз')
        if kind == 'rows11':
            place = values['review_place']
            if place in {v.value for v in ReviewPlace}:
                values['review_place'] = ReviewPlace(place).label_kz
            elif place is not None and place != (row['review_place'] or '').strip():
                raise HTTPException(400, 'Выберите место рассмотрения из списка / Қарау орнын тізімнен таңдаңыз')
        r = MODELS[kind].__table__
        await db.execute(update(r).where(r.c.id == row_id, r.c.template_direction_id == row['template_direction_id']).values(**values))
        return row
