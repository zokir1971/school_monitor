"""Per-user UI preference; availability is always checked by workspace service."""
from app.modules.users.enums import UserWorkspace
COOKIE='sm_workspace'

def requested_workspace(request,user):
    value=request.cookies.get(COOKIE)
    if value is not None:
        try:
            identity,choice=value.split(':',1)
            if identity!=str(user.id):return UserWorkspace.PRIMARY
            return UserWorkspace(choice)
        except (ValueError,AttributeError):return UserWorkspace.PRIMARY
    try:
        value=request.session.get('active_workspace')
        return UserWorkspace(value) if value else None
    except (ValueError,TypeError):return None

def save_workspace(request,response,user,workspace):
    # A late SessionMiddleware response can refresh its own session cookie,
    # but cannot overwrite this preference cookie written only by panel navigation.
    request.session['active_workspace']=workspace.value
    response.set_cookie(COOKIE,str(user.id)+':'+workspace.value,httponly=True,secure=request.url.scheme=='https',samesite='lax',path='/')
    response.headers['Cache-Control']='no-store'
    response.headers['Vary']='Cookie'
    return response
