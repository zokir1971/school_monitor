"""Render an authorized dashboard and keep its active-panel label in sync."""
from dataclasses import replace
from fastapi import HTTPException
from app.modules.users.enums import UserWorkspace,UserRole
from app.modules.users.workspace_choice import save_workspace
from app.routers.web.helpers.render import render

def render_dashboard(templates,request,name,ctx,workspace=UserWorkspace.PRIMARY):
    user=ctx['user'];context=getattr(request.state,'workspace_context',None)
    if context is None:raise HTTPException(403,'Workspace context required')
    if ((workspace==UserWorkspace.TEACHER and user.role==UserRole.TEACHER) or
        (workspace==UserWorkspace.STAFF and user.role==UserRole.SCHOOL_STAFF)):
        workspace=UserWorkspace.PRIMARY
    if not context.has_workspace(workspace):raise HTTPException(403,'Workspace unavailable')
    context=replace(context,active=workspace,items=[replace(item,is_active=item.code==workspace) for item in context.items])
    request.state.workspace_context=context
    response=render(templates,request,name,dict(ctx,workspace_context=context))
    return save_workspace(request,response,user,workspace)
