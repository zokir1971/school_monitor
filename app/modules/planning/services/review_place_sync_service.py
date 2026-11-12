from fastapi import HTTPException
from app.modules.planning.repositories.review_place_sync_repo import ReviewPlaceSyncRepo

class ReviewPlaceSyncService:
    @staticmethod
    async def sync_month(db, *, school_id, month_plan_id):
        context=await ReviewPlaceSyncRepo.month_context(db,school_id=school_id,month_plan_id=month_plan_id)
        if context is None:
            raise HTTPException(404,'Месячный план не найден / Айлық жоспар табылмады')
        if any(str(getattr(context[k],'value',context[k]))=='archived' for k in ('status','annual_status')):
            raise HTTPException(409,'Архивный план нельзя изменять / Мұрағат жоспарын өзгертуге болмайды')
        stats=await ReviewPlaceSyncRepo.sync(db,school_plan_id=context['school_plan_id'],month_plan_id=month_plan_id,locked=True)
        return context,stats
