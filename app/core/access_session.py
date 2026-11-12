"""Password-bound identity in Starlette's signed session; plain user_id is not auth."""
import hashlib
import hmac
import secrets
from collections.abc import Mapping
from app.core.config import get_settings


def credential_stamp(user):
    value = (str(user['id'])+'|'+user['password_hash']) if isinstance(user, Mapping) else (str(user.id)+'|'+user.password_hash)
    return hmac.new(str(get_settings().SECRET_KEY).encode(), value.encode(), hashlib.sha256).hexdigest()


def session_user_id(request):
    value = request.scope.get('session', {}).get('auth_user_id')
    return value if type(value) is int and value > 0 else None


def session_matches(request, user):
    if not user or not user.is_active or session_user_id(request) != user.id:
        return False
    saved = request.scope.get('session', {}).get('auth_credential_stamp')
    return isinstance(saved, str) and hmac.compare_digest(saved, credential_stamp(user))


def bind_session(request, user):
    request.session.clear()
    request.session['auth_user_id'] = user.id
    request.session['auth_credential_stamp'] = credential_stamp(user)


def csrf_token(request):
    value = request.session.get('access_recovery_csrf')
    if not isinstance(value, str) or len(value) < 32:
        value = secrets.token_urlsafe(32)
        request.session['access_recovery_csrf'] = value
    return value


def csrf_matches(request, received):
    saved = request.session.get('access_recovery_csrf')
    return isinstance(saved, str) and isinstance(received, str) and hmac.compare_digest(saved, received)
