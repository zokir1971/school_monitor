"""Edit one language of existing template text without replacing row identities."""
from fastapi import APIRouter,Depends,HTTPException,Query
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.planning.models import PlanDirection,PlanTemplateDirection,PlanTemplateRow4,PlanTemplateRow11
from app.modules.planning.content_i18n import content_text,content_revision,write_text
from app.modules.planning.template_samples import sample_text
from app.core.i18n import resolve_language,normalize_language
from app.routers.web.web_common import templates
from app.routers.web.helpers.render import render

router=APIRouter(prefix='/planning/super/content',tags=['Planning content languages'])
MODELS={'direction':PlanDirection,'template-direction':PlanTemplateDirection,'row4':PlanTemplateRow4,'row11':PlanTemplateRow11}
LABELS={
 'short_title':('Қысқаша атауы','Краткое название'),'full_title':('Толық атауы','Полное название'),
 'title_override':('Бағыттың атауы','Название направления'),
 'control_object':('Бақылау нысаны','Объект контроля'),'risk_text':('Мәселелер мен тәуекелдер','Проблемы и риски'),
 'decision_text':('Басқарушылық шешімдер','Управленческие решения'),'topic':('Тақырып','Тема'),
 'goal':('Мақсаты','Цель'),'control_type':('Бақылау түрі','Вид контроля'),
 'methods':('Әдістер','Методы'),'deadlines':('Мерзімдер','Сроки'),'responsibles':('Жауаптылар','Ответственные'),
 'review_place':('Қарау орны','Место рассмотрения'),'management_decision':('Басқарушылық шешім','Управленческое решение'),
 'second_control':('Қайта бақылау','Повторный контроль'),
}

async def load(db,kind,row_id,*,lock=False):
    model=MODELS.get(kind)
    if model is None:raise HTTPException(404,'Not found')
    row=await db.get(model,row_id,options=[raiseload('*')],with_for_update=lock,populate_existing=lock)
    if row is None:raise HTTPException(404,'Not found')
    return row

async def return_url(db,row):
    if isinstance(row,PlanDirection):return '/planning/super/directions'
    td=row if isinstance(row,PlanTemplateDirection)else await db.get(PlanTemplateDirection,row.template_direction_id,options=[raiseload('*')])
    return f'/planning/super/builder?template_id={td.template_id}&direction_id={td.direction_id}'

@router.get('/{kind}/{row_id}')
async def page(request:Request,kind:str,row_id:int,db:AsyncSession=Depends(get_db),user=Depends(require_roles(UserRole.SUPERUSER))):
    row=await load(db,kind,row_id);lang=resolve_language(request,user)
    return render(templates,request,'planning/super/content_language.html',dict(user=user,kind=kind,row_id=row_id,
        back=await return_url(db,row),content_language=lang,revision=content_revision(row,lang),
        fields=[dict(name=k,label=LABELS[k][0 if lang=='kk'else 1],value=content_text(row,k,lang) or (sample_text(row,k,lang) if k=='review_place' else ''))for k in row.__text_fields__]))

@router.post('/{kind}/{row_id}')
async def save(request:Request,kind:str,row_id:int,db:AsyncSession=Depends(get_db),user=Depends(require_roles(UserRole.SUPERUSER))):
    form=await request.form();lang=normalize_language(form.get('content_language'))
    if lang is None:raise HTTPException(422,'Invalid language')
    row=await load(db,kind,row_id,lock=True)
    if form.get('revision')!=content_revision(row,lang):raise HTTPException(409,'Строка изменена. Обновите страницу. / Жол өзгертілді. Бетті жаңартыңыз.')
    for field in row.__text_fields__:
        value=str(form.get(field,'')).strip()
        if len(value)>20000:raise HTTPException(422,'Text is too long')
        # A translation can be incomplete. Missing fields are visible as blanks,
        # and the opposite version is never substituted or erased.
        write_text(row,field,value,lang)
    back=await return_url(db,row)
    await db.commit()
    return RedirectResponse(back,303)


# Keep existing editor bookmarks safe after introducing language-specific storage.
# These routes are registered before the older editor's router.
legacy_router = APIRouter(prefix='/planning/super/builder')

@legacy_router.get('/{table_kind}/{row_id}/edit')
async def legacy_edit_page(request: Request, table_kind: str, row_id: int,
        template_id: int = Query(..., gt=0), direction_id: int = Query(..., gt=0),
        db: AsyncSession = Depends(get_db), user=Depends(require_roles(UserRole.SUPERUSER))):
    kind = {'rows4': 'row4', 'rows11': 'row11'}.get(table_kind)
    if kind is None:
        raise HTTPException(404, 'Not found')
    row = await load(db, kind, row_id)
    td = await db.get(PlanTemplateDirection, row.template_direction_id, options=[raiseload('*')])
    if td is None or td.template_id != template_id or td.direction_id != direction_id:
        raise HTTPException(404, 'Not found')
    return RedirectResponse(f'/planning/super/content/{kind}/{row_id}', 303)

@legacy_router.post('/{table_kind}/{row_id}/edit')
async def legacy_edit_submit(request: Request, table_kind: str, row_id: int,
        user=Depends(require_roles(UserRole.SUPERUSER))):
    # A pre-upgrade form has no language marker and cannot safely identify which
    # version its text belongs to. Require reopening it rather than guessing.
    message = ('Редактор обновлён. Откройте строку заново перед сохранением.'
        if resolve_language(request, user) == 'ru' else
        'Редактор жаңартылды. Сақтау алдында жолды қайта ашыңыз.')
    raise HTTPException(409, message)
