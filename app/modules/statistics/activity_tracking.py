"""Track committed school writes, never GETs or an unverified cookie.

Session-local listeners have request lifetime. Daily UPSERT happens after the
response body, is awaited (no orphan background task), and cannot undo a save.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy import event, func
from sqlalchemy.dialects.postgresql import insert
from app.modules.statistics.activity_tables import activity_days

logger = logging.getLogger(__name__)
LOCAL_TZ = timezone(timedelta(hours=5))
SCHOOL_ROLES = frozenset(('school_admin', 'school_staff', 'teacher'))


def module_for(path):
    for prefix, module in (
        ('/staff/reports', 'reports'), ('/staff/reviews', 'reviews'),
        ('/staff/tasks/review', 'reviews'), ('/staff/tasks', 'tasks'),
        ('/planning/school', 'planning'), ('/education', 'education'),
        ('/staff/school', 'staff'), ('/staff/assessment', 'assessment'),
        ('/assessment', 'assessment'),
    ):
        if path == prefix or path.startswith(prefix + '/'):
            return module
    return None


def verified_actor(request, user, *, login=False):
    role = getattr(user.role, 'value', user.role)
    if role in SCHOOL_ROLES and user.school_id and user.is_active:
        request.scope['_school_activity_actor'] = int(user.school_id)
        if login:
            request.scope['_school_activity_login'] = True


def observe_session(session, scope):
    """Only install for business POST/PUT/PATCH/DELETE requests."""
    dirty_transactions = set()

    def current(db):
        return db.get_nested_transaction() or db.get_transaction()

    def flushed(db, context):
        if db.new or db.deleted or any(db.is_modified(obj, include_collections=True) for obj in db.dirty):
            dirty_transactions.add(current(db))

    def executed(state):
        if not (state.is_insert or state.is_update or state.is_delete):
            return None
        result = state.invoke_statement()
        affected = getattr(result, 'rowcount', getattr(getattr(result, 'raw', None), 'rowcount', -1))
        if affected != 0:
            dirty_transactions.add(current(state.session))
        return result

    def committed(db):
        transaction = current(db)
        changed = transaction in dirty_transactions
        dirty_transactions.discard(transaction)
        if db.in_nested_transaction():
            if changed:
                dirty_transactions.add(transaction.parent)
        else:
            if changed:
                scope['_school_activity_committed'] = True
            dirty_transactions.clear()

    def rollback(db):
        transaction = current(db)
        if db.in_nested_transaction():
            dirty_transactions.discard(transaction)
        else:
            dirty_transactions.clear()

    callbacks = (('after_flush', flushed), ('do_orm_execute', executed),
                 ('after_commit', committed), ('after_rollback', rollback))
    for name, callback in callbacks:
        event.listen(session, name, callback, **({'retval': True} if name == 'do_orm_execute' else {}))
    return lambda: [event.remove(session, name, callback) for name, callback in callbacks]


async def record(factory, school_id, module, at):
    day = at.astimezone(LOCAL_TZ).date()
    stmt = insert(activity_days).values(school_id=school_id, day=day, module=module, first_at=at, last_at=at)
    stmt = stmt.on_conflict_do_update(
        index_elements=['school_id', 'day', 'module'],
        set_={'first_at': func.least(activity_days.c.first_at, stmt.excluded.first_at),
              'last_at': func.greatest(activity_days.c.last_at, stmt.excluded.last_at)},
    )
    async with factory() as db:
        await db.execute(stmt)
        await db.commit()


class SchoolActivityMiddleware:
    def __init__(self, app, factory=None):
        self.app, self.factory = app, factory

    async def __call__(self, scope, receive, send):
        module = module_for(scope.get('path', ''))
        login = scope.get('path') == '/login'
        if scope['type'] != 'http' or scope.get('method') not in ('POST', 'PUT', 'PATCH', 'DELETE') or not (module or login):
            return await self.app(scope, receive, send)
        status, redirect_error = 500, False

        async def capture(message):
            nonlocal status, redirect_error
            if message['type'] == 'http.response.start':
                status = message['status']
                from urllib.parse import urlsplit, parse_qs
                for key, value in message.get('headers', []):
                    if key.lower() == b'location':
                        target = urlsplit(value.decode('latin1'))
                        redirect_error = 'error' in parse_qs(target.query, keep_blank_values=True) or target.path == '/login'
            await send(message)

        await self.app(scope, receive, capture)
        school_id = scope.get('_school_activity_actor')
        kind = 'login' if login and scope.get('_school_activity_login') else module
        committed = scope.get('_school_activity_committed')
        if school_id and kind and 200 <= status < 400 and not redirect_error and (committed or kind == 'login'):
            if self.factory is None:
                from app.db.session import async_session_maker
                factory = async_session_maker
            else:
                factory = self.factory
            try:
                await asyncio.wait_for(record(factory, school_id, kind, datetime.now(timezone.utc)), timeout=3)
            except Exception:
                # No payloads, user IDs, SQL or sensitive parameters in this warning.
                logger.warning('School activity recording failed; activity statistics may be incomplete.')
