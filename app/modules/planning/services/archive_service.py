# app/modules/planning/services/archive_service.py
'''
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import PlanStatus, DocumentStatus
from ..repo import SchoolPlanRepo, DocumentRepo


class PlanningArchiveService:

    @staticmethod
    async def archive_school_plan(
        db: AsyncSession,
        *,
        plan_id: int,
    ):
        plan = await SchoolPlanRepo.get(db, plan_id)
        if not plan:
            raise HTTPException(404, "План не найден")

        if plan.status == PlanStatus.ARCHIVED:
            return

        now = datetime.utcnow()

        await SchoolPlanRepo.set_status(
            db,
            plan_id=plan_id,
            status=PlanStatus.ARCHIVED,
            archived_at=now,
        )

        documents = await DocumentRepo.list_by_plan(
            db,
            plan_id=plan_id,
            include_archived=True,
        )

        for doc in documents:
            if doc.status != DocumentStatus.ARCHIVED:
                await DocumentRepo.archive(db, document_id=doc.id)
'''
