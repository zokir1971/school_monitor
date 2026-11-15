from app.modules.planning.utils.month_schedule import MonthSchedule
import hashlib
import json
import logging
from collections import defaultdict
from fastapi import HTTPException
from app.modules.planning.enums import PlanStatus, AssignmentKind
from app.modules.planning.repositories.month_correction_repo import MonthCorrectionRepo as Repo

logger = logging.getLogger(__name__)
def value(v):
    return getattr(v, 'value', v)

class MonthCorrectionService:
    @staticmethod
    def revision(data):
        body = [dict(data['plan']), [dict(i) for i in data['items']], sorted([dict(a) for a in data['assignments']], key=lambda a:a['id'])]
        return hashlib.sha256(json.dumps(body, default=str, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    @classmethod
    def editor(cls, data):
        if data is None:
            return {}, ''
        planned, assigned = defaultdict(set), defaultdict(list)
        for row in data['planned']:
            planned[row['item_id']].add(value(row['role']))
        for row in data['assignments']:
            assigned[row['month_item_id']].append(row)
        result = {}
        for item in data['items']:
            selected = assigned[item['id']]
            primary = next((r['staff_role_id'] for r in selected if value(r['assignment_kind']) == 'primary'), None)
            options = [r for r in data['roles'] if value(r['role']) in planned[item['id']]]
            # A sole eligible role can be selected before the first draft save.
            if not selected and len(options) == 1:
                primary = options[0]['id']
            result[item['id']] = dict(primary=primary, co=[r['staff_role_id'] for r in selected if value(r['assignment_kind']) == 'co_executor'], options=options, all_options=data['roles'])
        return result, cls.revision(data)

    @classmethod
    async def save(cls, db, *, school_id, month_plan_id, school_plan_id, month, updates, form, actor_id, target_item_id=None):
        data = await Repo.snapshot(db, school_id=school_id, month_plan_id=month_plan_id, lock=True)
        if not data or data['plan']['school_plan_id'] != school_plan_id or data['plan']['month'] != month:
            raise HTTPException(404, 'План не найден / Жоспар табылмады')
        if any(value(data['plan'][key]) == 'archived' for key in ('status', 'annual_status')):
            raise HTTPException(409, 'Архивный план нельзя изменять / Мұрағат жоспарын өзгертуге болмайды')
        if form.get('plan_revision') != cls.revision(data):
            raise HTTPException(409, 'План изменён другим пользователем. Обновите страницу / Жоспар өзгерді. Бетті жаңартыңыз')
        items = {r['id']:r for r in data['items']}
        schedule=await MonthSchedule.evaluate(db,data)
        expected = schedule['visible_ids'] if target_item_id is None else {target_item_id}
        if not expected <= set(items) or len(updates) != len(expected) or {u.item_id for u in updates} != expected:
            raise HTTPException(400, 'Неполная форма плана. Обновите страницу / Жоспар нысаны толық емес')
        invalid=[u.item_id for u in updates if u.is_included and not items[u.item_id]['is_included'] and u.item_id not in schedule['eligible_ids']]
        if invalid:
            numbers=', '.join(map(str,invalid))
            raise HTTPException(409,f'Срок задачи не соответствует месяцу или квартальная задача уже выполнена: №{numbers}. Обновите страницу. / Тапсырма мерзімі айға сәйкес келмейді немесе тоқсандық тапсырма орындалған: №{numbers}. Бетті жаңартыңыз.')
        blocked = sorted(u.item_id for u in updates if not u.is_included and items[u.item_id]['is_included']
            and (items[u.item_id].get('exclusion_protected', False)
                or value(items[u.item_id].get('status')) not in (None, 'todo')
                or items[u.item_id].get('completed_at') is not None
                or items[u.item_id].get('executed_at') is not None))
        if blocked:
            numbers = ', '.join(map(str, blocked))
            raise HTTPException(409,
                f'Нельзя исключить начатые или выполненные задачи: №{numbers}. '
                'Их включение в план восстановлено. / '
                f'Басталған немесе орындалған тапсырмаларды алып тастауға болмайды: №{numbers}. '
                'Олардың жоспарға енгізілуі қалпына келтірілді.')
        roles = {r['id']:r for r in data['roles']}
        old_staff = {r['staff_role_id']:r['staff_member_id'] for r in data['assignments']}
        planned, old = defaultdict(set), defaultdict(list)
        for r in data['planned']:
            planned[r['item_id']].add(value(r['role']))
        for r in data['assignments']:
            old[r['month_item_id']].append((r['staff_role_id'],value(r['assignment_kind'])))
        changes, replace_ids, assignments, staff_ids, audit = [], [], [], set(), []
        for u in updates:
            item = items[u.item_id]
            # Keep prepared/history-bearing out-of-period rows unchanged on a full-page save.
            if target_item_id is None and u.item_id in schedule['warning_ids'] and not u.is_included and not item['is_included']:
                continue
            prefix = f'item_{u.item_id}_'
            inline = prefix+'primary' in form
            try:
                if inline:
                    primary = int(form[prefix+'primary']) if form.get(prefix+'primary') else None
                    co = sorted({int(v) for v in form.getlist(prefix+'co')})
                else:
                    primary = next((rid for rid,kind in old[u.item_id] if kind=='primary'), None)
                    co = [rid for rid,kind in old[u.item_id] if kind=='co_executor']
            except (TypeError, ValueError):
                raise HTTPException(400, f'Задача №{u.item_id}: неверный исполнитель / орындаушы қате')
            if u.is_included and not u.week_of_month:
                raise HTTPException(400, f'Задача №{u.item_id}: выберите неделю / аптаны таңдаңыз')
            if not primary and co:
                raise HTTPException(400, f'Задача №{u.item_id}: выберите ответственного / жауаптыны таңдаңыз')
            if u.is_included and value(data['plan']['status']) == 'active' and not primary:
                raise HTTPException(400, f'Задача №{u.item_id}: выберите ответственного / жауаптыны таңдаңыз')
            chosen = [] if inline else old[u.item_id]
            if inline and primary:
                role = roles.get(primary)
                if not role or value(role['role']) not in planned[u.item_id]:
                    raise HTTPException(400, f'Задача №{u.item_id}: ответственный не соответствует роли годового плана / жауапты жылдық жоспарға сәйкес емес')
                seen = {role['staff_member_id']}
                chosen.append((primary,'primary'))
                for role_id in co:
                    candidate = roles.get(role_id)
                    if not candidate:
                        raise HTTPException(400, f'Задача №{u.item_id}: сотрудник неактивен или из другой школы / қызметкер басқа мектептен')
                    if candidate['staff_member_id'] not in seen:
                        seen.add(candidate['staff_member_id']); chosen.append((role_id,'co_executor'))
            # Unincluded rows may retain old inactive assignments without revalidation.
            if not u.is_included and target_item_id is None:
                chosen = old[u.item_id]
            assignment_changed = set(chosen) != set(old[u.item_id])
            record = u.model_dump()
            record.pop('item_id')
            record['responsible_role'] = roles[primary]['role'] if inline and primary and (u.is_included or target_item_id is not None) else item['responsible_role']
            record['responsible_user_id'] = roles[primary]['user_id'] if inline and primary and (u.is_included or target_item_id is not None) else item['responsible_user_id']
            changed = any(record[key] != item[key] for key in record)
            if changed or assignment_changed:
                changes.append({'_item_id':u.item_id, **{'_'+key:v for key,v in record.items()}})
                audit.append(dict(item_id=u.item_id, before={k:item[k] for k in record}, after=record, assignees_before=old[u.item_id], assignees_after=chosen))
                for role_id, _ in old[u.item_id] + chosen:
                    if role_id in roles:
                        staff_ids.add(roles[role_id]['staff_member_id'])
                    elif role_id in old_staff:
                        staff_ids.add(old_staff[role_id])
            if assignment_changed:
                replace_ids.append(u.item_id)
                assignments.extend(dict(month_item_id=u.item_id, staff_role_id=rid, assignment_kind=AssignmentKind(kind), assigned_by_user_id=actor_id) for rid,kind in chosen)
        reason = str(form.get('correction_reason') or '').strip()
        if len(reason) > 1000:
            raise HTTPException(400, 'Причина исправления: не более 1000 символов / Түзету себебі: 1000 таңбадан аспауы керек')
        if changes and value(data['plan']['status']) == 'active' and not reason:
            raise HTTPException(400, 'Укажите причину исправления / Түзету себебін көрсетіңіз')
        await Repo.apply(db, updates=changes, assignment_ids=replace_ids, assignments=assignments, notification_staff_ids=staff_ids, month_plan_id=month_plan_id)
        return dict(actor_id=actor_id, plan_id=month_plan_id, reason=reason, changes=audit)

    @staticmethod
    def log_committed(audit):
        logger.info('MONTH_PLAN_CORRECTION actor=%s plan=%s changed=%s',
            audit.get('actor_id'), audit.get('plan_id'), len(audit.get('changes') or []))
        from app.modules.planning.utils.correction_audit_log import write_audit
        write_audit(audit)
