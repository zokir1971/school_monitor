# app/routers/web/education/__init__.py

from fastapi import APIRouter, Depends
from app.core.feature_access import education_dependency
from app.modules.users.deps import get_current_user
from .teaching_load_web import router as teaching_load_router
from .subject_reference_web import router as subject_reference_router


router = APIRouter(dependencies=[Depends(education_dependency(get_current_user))])

router.include_router(teaching_load_router)
router.include_router(subject_reference_router)

from .nobd_import_web import router as nobd_import_router
router.include_router(nobd_import_router)

from .class_curriculum_web import router as class_curriculum_router
router.include_router(class_curriculum_router)
