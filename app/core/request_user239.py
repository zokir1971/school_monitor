"""Reuse middleware authentication within one ASGI request, never across requests."""
from dataclasses import dataclass

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.core.access_session import session_matches, session_user_id
from app.modules.users.models import User

_KEY = '_sm_verified_request_user239'


@dataclass(frozen=True)
class _VerifiedUser:
    user: User
    user_id: int
    stamp: str


def clear_verified_user(request: Request) -> None:
    request.scope.pop(_KEY, None)


def remember_verified_user(request: Request, user: User) -> None:
    if session_matches(request, user):
        request.scope[_KEY] = _VerifiedUser(
            user=user,
            user_id=user.id,
            stamp=request.scope['session']['auth_credential_stamp'],
        )


async def reuse_verified_user(request: Request, db: AsyncSession) -> User | None:
    cached = request.scope.get(_KEY)
    if type(cached) is not _VerifiedUser:
        return None
    session = request.scope.get('session', {})
    if (session_user_id(request) != cached.user_id
            or session.get('auth_credential_stamp') != cached.stamp):
        return None
    state = inspect(cached.user)
    # Only the clean, fully loaded object from the closed middleware session.
    # An existing endpoint-session identity takes its original SELECT path.
    if (not state.detached or state.modified or state.expired_attributes
            or state.key in db.identity_map):
        return None
    if not session_matches(request, cached.user):
        return None
    # Keep a normal session-bound ORM User for existing routes and writes.
    # load=False copies verified scalar state without a SELECT or dirty history.
    return await db.merge(cached.user, load=False)
