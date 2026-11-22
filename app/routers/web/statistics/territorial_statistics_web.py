from urllib.parse import urlencode
from fastapi import APIRouter,Depends,Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.modules.users.deps import require_roles
from app.modules.users.enums import UserRole
from app.modules.statistics.territorial_service import TerritorialStatisticsService
from app.routers.web.helpers.render import render
from app.routers.web.web_common import templates

router=APIRouter(prefix='/statistics',tags=['Statistics.Territory.Web'])

@router.get('/territory',name='territorial_statistics_page',response_class=HTMLResponse)
async def territorial_statistics_page(request:Request,db:AsyncSession=Depends(get_db),
                                     user=Depends(require_roles(UserRole.SUPERUSER,UserRole.DISTRICT_ADMIN,UserRole.REGION_ADMIN))):
    data=await TerritorialStatisticsService.page(db,user,request.query_params)
    filters={key:value for key,value in data.items()if key in ('year','month','region_id','direction_id','district_id','school_id','view','sort','order','attention','q')and value is not None}
    def link(**changes):
        values=dict(filters,page=1);values.update(changes)
        return '/statistics/territory?'+urlencode({k:v for k,v in values.items()if v is not None and v!=''})
    response=render(templates,request,'statistics/territorial.html',dict(user=user,**data,link=link))
    response.headers['Cache-Control']='no-store'
    return response
