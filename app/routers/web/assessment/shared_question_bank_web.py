"""Authenticated staff/teacher read-only entry to the shared READY bank."""
from fastapi import APIRouter, Depends, Request
from app.db.session import get_db
from app.modules.assessment.helpers.bank_access import require_bank_reader
from app.routers.web.assessment.teacher_question_bank_web import teacher_question_bank_catalog_page

router = APIRouter(prefix='/assessment/question-bank', tags=['shared-question-bank'])

@router.get('/catalog', name='shared_question_bank_catalog')
async def catalog(request: Request, subject_id: str | None = None,
                  grade_level: str | None = None, quarter: str | None = None,
                  objective_id: str | None = None, education_track: str | None = None,
                  offset: int = 0, db=Depends(get_db), user=Depends(require_bank_reader)):
    return await teacher_question_bank_catalog_page(request=request, subject_id=subject_id,
        grade_level=grade_level, quarter=quarter, objective_id=objective_id, education_track=education_track, offset=offset, db=db, user=user)
