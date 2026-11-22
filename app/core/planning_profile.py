"""Opt-in, loopback-only counters for planning saves and redirected GET pages.

No SQL text, parameters, cookies, headers or user/account data are recorded.
Disabled by default; it neither opens a DB connection nor creates a report.
"""
from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time

_current = ContextVar('school_monitor_navigation_profile', default=None)
_plan_path = re.compile(r'^/planning/school/plan/[1-9][0-9]*$')
_session_observer_attached = False


_get_paths = [
    re.compile(r'^/planning/school/[1-9][0-9]*/(?:preview|pdf)$'),
    re.compile(r'^/planning/school/monthly/?$'),
    re.compile(r'^/planning/school/monthly/[1-9][0-9]*/assignees$'),
    re.compile(r'^/planning/school/[1-9][0-9]*/direction/[1-9][0-9]*(?:/rows11/[1-9][0-9]*/edit)?$'),
]
_post_paths = [
    re.compile(r'^/planning/school/monthly/[1-9][0-9]*/(?:save|submit|assignees)$'),
    re.compile(r'^/planning/school/[1-9][0-9]*/direction/[1-9][0-9]*/save$'),
    re.compile(r'^/planning/school/[1-9][0-9]*/direction/[1-9][0-9]*/rows11/[1-9][0-9]*/edit$'),
]


def selected_scope(scope):
    if scope.get('type') != 'http' or (scope.get('client') or ('',0))[0] not in ('127.0.0.1','::1'):
        return False
    path=scope.get('path','')
    if scope.get('method') == 'POST':
        return any(pattern.fullmatch(path) for pattern in _post_paths)
    if scope.get('method') != 'GET':
        return False
    return (path in ('/dashboards/l3','/planning/school/','/planning/school')
            or bool(_plan_path.fullmatch(path))
            or any(pattern.fullmatch(path) for pattern in _get_paths))


@contextmanager
def measure_export_phase(name):
    """Measure fixed phase names only; no request/content values enter reports."""
    sample = _current.get()
    if sample is None or name not in ('export_data', 'preview_render', 'pdf_render', 'excel_data', 'excel_build', 'excel_import', 'excel_styles', 'excel_rows', 'excel_cells', 'excel_finalize'):
        yield
        return
    started = time.perf_counter()
    sql_before = sample['sql_count']
    sql_ms_before = sample['sql_ms']
    try:
        yield
    finally:
        result = sample['export_phases'].setdefault(name, dict(calls=0, total_ms=0.0, sql_count=0, sql_ms=0.0))
        result['calls'] += 1
        result['total_ms'] = round(result['total_ms'] + (time.perf_counter()-started)*1000, 2)
        result['sql_count'] += sample['sql_count']-sql_before
        result['sql_ms'] = round(result['sql_ms']+sample['sql_ms']-sql_ms_before, 2)



# Process-local HMAC lets diagnostics match selections without logging filter
# values, territorial/user identifiers or school search text.
_excel_selection_secret = None

def record_excel_context(role, language, kind, selection, sheets):
    sample = _current.get()
    if sample is None:
        return
    import hashlib
    import hmac
    import secrets
    global _excel_selection_secret
    if _excel_selection_secret is None:
        _excel_selection_secret = secrets.token_bytes(32)
    encoded = json.dumps(selection, sort_keys=True, ensure_ascii=False, default=str).encode('utf-8')
    sample['excel_context'] = {
        'role': role if role in ('superuser','region_admin','district_admin') else 'other',
        'language': language if language in ('ru','kk') else 'other',
        'kind': kind,
        'selection_key': hmac.new(_excel_selection_secret, encoded, hashlib.sha256).hexdigest()[:24],
        'sheets': [{'view': view, 'rows': len(rows)} for view, rows in sheets],
    }

def attach_observers(engine):
    global _session_observer_attached
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    if getattr(engine.sync_engine,'_sm_navigation_profile_attached',False):
        return
    def before(conn,cursor,statement,parameters,context,executemany):
        sample=_current.get()
        if sample is not None:
            sample['sql_count']+=1
            kind=statement.lstrip().split(None,1)[0].upper() if statement.strip() else 'OTHER'
            sample['sql_kinds'][kind if kind in ('SELECT','INSERT','UPDATE','DELETE') else 'OTHER']+=1
            context._sm_navigation_for_update=bool(re.search(r'\bFOR\s+UPDATE\b',statement,re.I))
            if context._sm_navigation_for_update:
                sample['for_update_count']+=1
            context._sm_navigation_started=time.perf_counter()
    def after(conn,cursor,statement,parameters,context,executemany):
        sample=_current.get()
        if sample is not None and hasattr(context,'_sm_navigation_started'):
            elapsed=(time.perf_counter()-context._sm_navigation_started)*1000
            sample['sql_ms']+=elapsed
            if getattr(context,'_sm_navigation_for_update',False):
                sample['for_update_ms']+=elapsed
    def loaded(session,instance):
        sample=_current.get()
        if sample is not None:
            sample['loaded_models'][type(instance).__name__]+=1
    def orm_execute(state):
        sample=_current.get()
        if sample is not None and state.is_relationship_load:
            sample['relationship_load_count']+=1
    def before_commit(session):
        sample=_current.get()
        if sample is not None:
            sample['commit_count']+=1
            session.info['_sm_save_commit']=(sample,time.perf_counter())
    def after_commit(session):
        marker=session.info.pop('_sm_save_commit',None)
        if marker is not None:
            sample,started=marker
            sample['commit_ms']+=(time.perf_counter()-started)*1000
    def after_rollback(session):
        session.info.pop('_sm_save_commit',None)
    event.listen(engine.sync_engine,'before_cursor_execute',before)
    event.listen(engine.sync_engine,'after_cursor_execute',after)
    if not _session_observer_attached:
        event.listen(Session,'loaded_as_persistent',loaded)
        event.listen(Session,'do_orm_execute',orm_execute)
        event.listen(Session,'before_commit',before_commit)
        event.listen(Session,'after_commit',after_commit)
        event.listen(Session,'after_rollback',after_rollback)
        _session_observer_attached=True
    engine.sync_engine._sm_navigation_profile_attached=True


def append_report(path,sample):
    data=(json.dumps(sample,ensure_ascii=False)+'\n').encode('utf-8')
    descriptor=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:
        os.write(descriptor,data)
    finally:
        os.close(descriptor)


class PlanningProfileMiddleware:
    def __init__(self,app,report_path,phase='unspecified'):
        self.app=app
        self.report_path=Path(report_path)
        self.phase=phase

    async def __call__(self,scope,receive,send):
        if not selected_scope(scope):
            return await self.app(scope,receive,send)
        sample=dict(version=204,phase=self.phase,method=scope['method'],time_utc=datetime.now(timezone.utc).isoformat(),
                    path=scope['path'],status=500,sql_count=0,sql_ms=0.0,
                    sql_kinds=Counter(),for_update_count=0,for_update_ms=0.0,
                    relationship_load_count=0,commit_count=0,commit_ms=0.0,
                    loaded_models=Counter(),response_bytes=0,export_phases={})
        started=time.perf_counter()
        token=_current.set(sample)
        async def counted_send(message):
            if message['type']=='http.response.start':
                sample['status']=message['status']
            elif message['type']=='http.response.body':
                sample['response_bytes']+=len(message.get('body',b''))
            await send(message)
        try:
            await self.app(scope,receive,counted_send)
        except BaseException as exc:
            sample['error_type']=type(exc).__name__
            raise
        finally:
            sample['total_ms']=round((time.perf_counter()-started)*1000,2)
            sample['sql_ms']=round(sample['sql_ms'],2)
            sample['for_update_ms']=round(sample['for_update_ms'],2)
            sample['commit_ms']=round(sample['commit_ms'],2)
            sample['orm_objects']=sum(sample['loaded_models'].values())
            _current.reset(token)
            try:
                append_report(self.report_path,sample)
            except OSError:
                # Diagnostics must not turn a successful page into an error.
                print('Planning profile: could not append the diagnostic report.')


def install_planning_profile(app):
    if os.environ.get('SM_PLANNING_PROFILE') != '1':
        return False
    if getattr(app.state,'planning_navigation_profile',False):
        return True
    from app.db.session import engine
    folder=Path.home()/'Downloads'
    folder.mkdir(parents=True,exist_ok=True)
    phase=os.environ.get('SM_PLANNING_PROFILE_LABEL','unspecified')
    if phase not in ('before','after','save'):
        phase='unspecified'
    path=folder/('planning_export204_'+phase+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+str(os.getpid())+'.jsonl')
    attach_observers(engine)
    app.add_middleware(PlanningProfileMiddleware,report_path=str(path),phase=phase)
    app.state.planning_navigation_profile=True
    print('Planning export profile enabled. Report: '+str(path))
    return True
