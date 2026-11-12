"""Review and delete an owned, unused draft without changing bank questions."""
import hashlib
import json
from app.modules.assessment.services import work_plan_service as work,work_plan_position_service as positions
from app.modules.assessment.repositories import work_plan_repo as repo
from app.modules.assessment.helpers.work_plan_positions import composition_revision


async def review(db,user,plan_id,lock=False):
    plan=await work.own(db,user,plan_id,lock)
    work.editable(plan)
    await positions.ensure_unused(db,plan)
    rows=await repo.items(db,plan.id)
    data=dict(composition=composition_revision(plan,rows),updated=str(plan.updated_at),
              title=plan.title,kk=plan.title_kk,ru=plan.title_ru)
    revision=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return dict(plan=plan,card_count=len(rows),source_count=len({r.bank_item_id for r in rows}),revision=revision)


async def remove(db,user,plan_id,revision):
    data=await review(db,user,plan_id,True)
    if revision!=data['revision']:
        raise positions.CompositionChanged('Комплект изменился. Проверьте его перед удалением. / Жинақ өзгерді. Жою алдында оны тексеріңіз.')
    await work.delete_draft(db,user,plan_id)
