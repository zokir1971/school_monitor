# app/routers/web/assessment/region_question_bank_expert_web.py

from __future__ import annotations

import hmac
import secrets
from typing import cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.assessment.models_question_bank_experts import QuestionBankExpertSpecialty, QuestionBankExpertRule
from app.modules.assessment.schemas.question_bank_expert_schemas import (
    QuestionBankExpertCreateDTO,
    QuestionBankExpertUpdateDTO,
)
from app.modules.assessment.services.question_bank_expert_service import (
    QuestionBankExpertError,
    QuestionBankExpertNotFoundError,
    QuestionBankExpertService,
)
from app.modules.education.models import Subject
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.users.models import User
from app.routers.web.helpers.render import render
from app.routers.web.helpers.request import parse_optional_int
from app.routers.web.web_common import templates

router = APIRouter(
    prefix="/region/assessment/question-bank/experts",
    tags=["region-question-bank-experts"],
)

EXPERT_INSTRUCTION_LANGUAGES = {
    'all': 'Все языки обучения',
    'kz': 'Казахский',
    'ru': 'Русский',
    'uz': 'Узбекский',
    'ug': 'Уйгурский',
    'tg': 'Таджикский',
}

# ============================================================
# HELPERS
# ============================================================


def _require_region_id(user: User) -> int:
    """
    REGION_ADMIN должен иметь региональную область доступа.
    """

    if user.region_id is None:
        raise HTTPException(
            status_code=403,
            detail="Пайдаланушыға өңір бекітілмеген.",
        )

    return cast(int, user.region_id)


# ============================================================
# LIST
# ============================================================


@router.get(
    "",
    name="region_question_bank_expert_list",
    response_class=HTMLResponse,
)
async def region_question_bank_expert_list(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    district_id = parse_optional_int(
        request.query_params.get("district_id")
    )

    subject_id = parse_optional_int(
        request.query_params.get("subject_id")
    )

    status = (
            request.query_params.get("status") or ""
    ).strip()

    if status == "active":
        active_only = True
    elif status == "inactive":
        active_only = False
    else:
        active_only = None

    page = await QuestionBankExpertService.get_page(
        db,
        region_id=region_id,
        district_id=district_id,
        subject_id=subject_id,
        active_only=active_only,
    )

    return render(
        templates,
        request,
        "region/assessment/question_bank_experts/list.html",
        {
            "user": user,
            "page": page,
            "district_id": district_id,
            "subject_id": subject_id,
            "status": status,
        },
    )


# ============================================================
# CREATE PAGE
# ============================================================


@router.get(
    "/create",
    name="region_question_bank_expert_create_page",
    response_class=HTMLResponse,
)
async def region_question_bank_expert_create_page(
        request: Request,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    options = await QuestionBankExpertService.get_form_options(
        db,
        region_id=region_id,
    )

    return render(
        templates,
        request,
        "region/assessment/question_bank_experts/create.html",
        {
            "user": user,
            "options": options,
        },
    )


# ============================================================
# CREATE
# ============================================================


@router.post(
    "/create",
    name="region_question_bank_expert_create",
)
async def region_question_bank_expert_create(
        request: Request,

        school_id: int = Form(...),
        specialty_id: int = Form(...),

        iin: str = Form(...),
        full_name: str = Form(...),

        phone: str | None = Form(default=None),
        email: str | None = Form(default=None),

        position_text: str | None = Form(default=None),
        education_text: str | None = Form(default=None),
        specialty_text: str | None = Form(default=None),
        qualification_category_text: str | None = Form(default=None),

        ped_experience_years: int | None = Form(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    dto = QuestionBankExpertCreateDTO(
        school_id=school_id,
        subject_id=None,
        specialty_id=specialty_id,

        iin=iin,
        full_name=full_name,

        phone=phone,
        email=email,

        position_text=position_text,
        education_text=education_text,
        specialty_text=specialty_text,
        qualification_category_text=(
            qualification_category_text
        ),

        ped_experience_years=ped_experience_years,
    )

    try:
        expert = await QuestionBankExpertService.create(
            db,
            region_id=region_id,
            created_by_user_id=user.id,
            dto=dto,
        )

    except QuestionBankExpertError as exc:
        options = await QuestionBankExpertService.get_form_options(
            db,
            region_id=region_id,
        )

        return render(
            templates,
            request,
            "region/assessment/question_bank_experts/create.html",
            {
                "user": user,
                "options": options,
                "form": dto,
                "error": str(exc),
            },
            status_code=400,
        )

    return RedirectResponse(
        url=request.url_for(
            "region_question_bank_expert_detail",
            expert_id=expert.id,
        ),
        status_code=303,
    )


# ============================================================
# DETAIL
# ============================================================


@router.get(
    "/{expert_id}",
    name="region_question_bank_expert_detail",
    response_class=HTMLResponse,
)
async def region_question_bank_expert_detail(
        request: Request,
        expert_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    try:
        expert = await QuestionBankExpertService.get_detail(
            db,
            expert_id=expert_id,
            region_id=region_id,
        )

    except QuestionBankExpertNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return render(
        templates,
        request,
        "region/assessment/question_bank_experts/detail.html",
        {
            "user": user,
            "expert": expert,
        },
    )


# ============================================================
# EDIT PAGE
# ============================================================
@router.get(
    "/{expert_id}/edit",
    name="region_question_bank_expert_edit_page",
    response_class=HTMLResponse,
)
async def region_question_bank_expert_edit_page(
        request: Request,
        expert_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    try:
        expert = await QuestionBankExpertService.get_detail(
            db,
            expert_id=expert_id,
            region_id=region_id,
        )

    except QuestionBankExpertNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    options = await QuestionBankExpertService.get_form_options(
        db,
        region_id=region_id,
    )

    form = QuestionBankExpertUpdateDTO(
        specialty_id=expert.specialty_id,
        school_id=expert.school_id,
        full_name=expert.full_name,
        phone=expert.phone,
        email=expert.email,
        position_text=expert.position_text,
        education_text=expert.education_text,
        specialty_text=expert.specialty_text,
        qualification_category_text=(
            expert.qualification_category_text
        ),
        ped_experience_years=expert.ped_experience_years,
    )

    return render(
        templates,
        request,
        "region/assessment/question_bank_experts/edit.html",
        {
            "user": user,
            "expert": expert,
            "form": form,
            "options": options,
            "error": None,
        },
    )


# ============================================================
# UPDATE
# ============================================================


@router.post(
    "/{expert_id}/edit",
    name="region_question_bank_expert_update",
)
async def region_question_bank_expert_update(
        request: Request,
        expert_id: int,

        school_id: int = Form(...),
        full_name: str = Form(...),
        specialty_id: int = Form(...),

        phone: str | None = Form(default=None),
        email: str | None = Form(default=None),

        position_text: str | None = Form(default=None),
        education_text: str | None = Form(default=None),
        specialty_text: str | None = Form(default=None),
        qualification_category_text: str | None = Form(default=None),

        ped_experience_years: int | None = Form(default=None),

        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    dto = QuestionBankExpertUpdateDTO(
        specialty_id=specialty_id,
        school_id=school_id,
        full_name=full_name,

        phone=phone,
        email=email,

        position_text=position_text,
        education_text=education_text,
        specialty_text=specialty_text,
        qualification_category_text=(
            qualification_category_text
        ),

        ped_experience_years=ped_experience_years,
    )

    try:
        await QuestionBankExpertService.update(
            db,
            expert_id=expert_id,
            region_id=region_id,
            dto=dto,
        )

    except QuestionBankExpertNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except QuestionBankExpertError as exc:
        expert = await QuestionBankExpertService.get_detail(
            db,
            expert_id=expert_id,
            region_id=region_id,
        )

        options = await QuestionBankExpertService.get_form_options(
            db,
            region_id=region_id,
        )

        return render(
            templates,
            request,
            "region/assessment/question_bank_experts/edit.html",
            {
                "user": user,
                "expert": expert,
                "options": options,
                "form": dto,
                "error": str(exc),
            },
            status_code=400,
        )

    return RedirectResponse(
        url=request.url_for(
            "region_question_bank_expert_detail",
            expert_id=expert_id,
        ),
        status_code=303,
    )


# ============================================================
# DEACTIVATE
# ============================================================


@router.post(
    "/{expert_id}/deactivate",
    name="region_question_bank_expert_deactivate",
)
async def region_question_bank_expert_deactivate(
        request: Request,
        expert_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    try:
        await QuestionBankExpertService.deactivate(
            db,
            expert_id=expert_id,
            region_id=region_id,
            deactivated_by_user_id=user.id,
        )

    except QuestionBankExpertNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except QuestionBankExpertError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=request.url_for(
            "region_question_bank_expert_detail",
            expert_id=expert_id,
        ),
        status_code=303,
    )


# ============================================================
# ACTIVATE
# ============================================================


@router.post(
    "/{expert_id}/activate",
    name="region_question_bank_expert_activate",
)
async def region_question_bank_expert_activate(
        request: Request,
        expert_id: int,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(
            require_roles(UserRole.REGION_ADMIN)
        ),
):
    region_id = _require_region_id(user)

    try:
        await QuestionBankExpertService.activate(
            db,
            expert_id=expert_id,
            region_id=region_id,
        )

    except QuestionBankExpertNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except QuestionBankExpertError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    return RedirectResponse(
        url=request.url_for(
            "region_question_bank_expert_detail",
            expert_id=expert_id,
        ),
        status_code=303,
    )


@router.get('/policy', name='region_expert_policy_page')
async def policy_page(request: Request, db: AsyncSession = Depends(get_db),
                      user: User = Depends(require_roles(UserRole.REGION_ADMIN, UserRole.SUPERUSER))):
    specialties = (await db.execute(
        select(QuestionBankExpertSpecialty).order_by(QuestionBankExpertSpecialty.name_ru))).scalars().all()
    subjects = (await db.execute(select(Subject).order_by(Subject.name_ru))).scalars().all()
    rules = (await db.execute(select(QuestionBankExpertRule).order_by(
        QuestionBankExpertRule.specialty_id, QuestionBankExpertRule.subject_id,
        QuestionBankExpertRule.grade_from))).scalars().all()
    csrf_token = request.cookies.get('qb_expert_policy_csrf') or secrets.token_urlsafe(32)
    response = render(templates, request, 'region/assessment/question_bank_experts/policy.html', {
        'csrf_token': csrf_token, 'user': user, 'specialties': specialties, 'subjects': subjects, 'rules': rules,
        'languages': EXPERT_INSTRUCTION_LANGUAGES, 'can_edit': getattr(
            user.role, 'value', user.role) == UserRole.SUPERUSER.value,
        'subject_names': {s.id: (s.name_ru or s.name_kz) for s in subjects},
        'specialty_names': {s.id: s.name_ru for s in specialties},
    })
    response.set_cookie('qb_expert_policy_csrf', csrf_token, httponly=True, samesite='strict',
                        secure=request.url.scheme == 'https', path=request.url.path)
    return response


def verify_csrf(request, token):
    expected = request.cookies.get('qb_expert_policy_csrf', '')
    if not expected or not hmac.compare_digest(expected, token):
        raise HTTPException(403, 'Обновите страницу перед сохранением.')


@router.post('/policy/specialty', name='region_expert_policy_specialty_save')
async def save_specialty(request: Request, csrf_token: str = Form(...), name_ru: str = Form(...),
                         name_kz: str = Form(...),
                         code: str = Form(...), specialty_id: int = Form(0), active: bool = Form(False),
                         db: AsyncSession = Depends(get_db),
                         _user: User = Depends(require_roles(UserRole.SUPERUSER))):
    verify_csrf(request, csrf_token)
    import re
    code = code.strip()
    name_ru = name_ru.strip()
    name_kz = name_kz.strip()
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', code) or not name_ru or not name_kz or max(len(name_ru),
                                                                                            len(name_kz)) > 200:
        raise HTTPException(400, 'Укажите код латиницей и названия до 200 символов.')
    row = await db.get(QuestionBankExpertSpecialty, specialty_id) if specialty_id else QuestionBankExpertSpecialty()
    if row is None:
        raise HTTPException(404, 'Специальность не найдена.')
    row.code = code
    row.name_ru = name_ru
    row.name_kz = name_kz
    row.is_active = active
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(400, 'Код специальности уже существует.') from exc
    return RedirectResponse(request.url_for('region_expert_policy_page'), 303)


@router.post('/policy/rule', name='region_expert_policy_rule_save')
async def save_rule(request: Request, csrf_token: str = Form(...), specialty_id: int = Form(...),
                    subject_id: int = Form(...),
                    grade_from: int = Form(...), grade_to: int = Form(...),
                    instruction_language: str = Form(...), rule_id: int = Form(0), active: bool = Form(False),
                    db: AsyncSession = Depends(get_db),
                    _user: User = Depends(require_roles(UserRole.SUPERUSER))):
    verify_csrf(request, csrf_token)
    if not 1 <= grade_from <= grade_to <= 12 or instruction_language not in EXPERT_INSTRUCTION_LANGUAGES:
        raise HTTPException(400, 'Проверьте диапазон классов и язык обучения.')
    if not await db.get(Subject, subject_id) or not await db.get(QuestionBankExpertSpecialty, specialty_id):
        raise HTTPException(400, 'Предмет или специальность не найдены.')
    row = await db.get(QuestionBankExpertRule, rule_id) if rule_id else QuestionBankExpertRule()
    if row is None:
        raise HTTPException(404, 'Правило не найдено.')
    row.specialty_id = specialty_id
    row.subject_id = subject_id
    row.grade_from = grade_from
    row.grade_to = grade_to
    row.instruction_language = instruction_language
    row.is_active = active
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(400, 'Такое правило уже существует.') from exc
    return RedirectResponse(request.url_for('region_expert_policy_page'), 303)
