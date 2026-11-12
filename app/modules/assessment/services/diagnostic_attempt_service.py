"""Pupil/subject serialization, immutable shuffles, server-authoritative deadlines."""
from datetime import datetime, timedelta, timezone
from app.modules.assessment.helpers.diagnostic_period import start_block
import logging
from app.modules.assessment.repositories import diagnostic_attempt_repo as repo
from app.modules.assessment.models_diagnostic_attempts import DiagnosticAttempt as Attempt
from app.modules.assessment.helpers.diagnostic_presentation import compile_presentation, validate_responses


class AttemptError(ValueError):
    def __init__(self, code, status=400):
        self.code=code;self.status=status;super().__init__(code)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def now(db):
    return utc(await repo.clock(db))


async def authorize(db, identity, lock=False):
    # Session lock serializes start/save against organizer close and code regeneration.
    sid=await repo.identity_session(db,identity)
    if sid is None:raise AttemptError('access',401)
    if await repo.authorized_session(db,sid,lock) is None:raise AttemptError('access',401)
    person=await repo.identity_person(db,identity,lock)
    if person is None:raise AttemptError('access',401)
    return person


async def expire(db, participant_id=None, session_id=None):
    at=await now(db)
    await repo.expire(db,at,participant_id,session_id)


from app.modules.assessment.helpers.assessment_names import subject_title

async def subject_list(db, person):
    await expire(db,person.id)
    rows=await repo.subjects(db,person.session_id)
    attempts=await repo.attempt_states(db,person.id)
    session=await repo.session(db,person.session_id)
    at=await now(db)
    result=[];available=not any(a.status=='active' for a in attempts.values())
    for row in rows:
        a=attempts.get(row.id);assignment=person.assignments[str(row.source_plan_id)]
        state=a.status if a else ('period_closed' if session.status=='closed' else start_block(session,at,row.minutes) or ('ready' if available else 'locked'))
        result.append(dict(id=row.id,attempt_id=a.id if a else None,state=state,minutes=row.minutes,
                           name=subject_title(row,assignment['language']),**assignment))
    return result


async def start(db, identity, subject_id):
    person=await authorize(db,identity,True)
    listing=await subject_list(db,person)
    info=next((r for r in listing if r['id']==subject_id),None)
    if info is None:raise AttemptError('subject',404)
    if info['attempt_id']:
        if info['state']=='active':return info['attempt_id']
        raise AttemptError('finished',409)
    if info['state']!='ready':raise AttemptError(info['state'] if info['state'] in ('not_open','period_closed','insufficient') else 'sequence',409)
    subject=await repo.subject(db,subject_id,person.session_id)
    assignment=person.assignments[str(subject.source_plan_id)]
    selected=[s for s in subject.snapshots if s['variant_no']==assignment['variant']]
    from app.modules.assessment.helpers.work_plan_presentation import ordered_items
    from types import SimpleNamespace
    # Same curriculum/difficulty/type ordering as the paper document.
    sorted_rows=ordered_items([SimpleNamespace(**s,id=n) for n,s in enumerate(selected)])
    selected=[selected[s.id] for s in sorted_rows]
    if not selected:raise AttemptError('configuration',409)
    try:presentation,private=compile_presentation(selected,assignment['language'])
    except (ValueError,KeyError,TypeError) as exc:
        logging.getLogger(__name__).warning('Diagnostic presentation blocked: subject=%s reason=%s',subject.id,type(exc).__name__)
        raise AttemptError('configuration',409) from None
    at=await now(db)
    session=await repo.session(db,person.session_id)
    reason='period_closed' if session.status=='closed' else start_block(session,at,subject.minutes)
    if reason:raise AttemptError(reason,409)
    attempt=Attempt(participant_id=person.id,diagnostic_subject_id=subject.id,status='active',started_at=at,
                    deadline_at=at+timedelta(minutes=subject.minutes),version=0,presentation=presentation,
                    private_data=private,responses={})
    await repo.save(db,attempt);return attempt.id


async def owned_attempt(db, identity, attempt_id, lock=False):
    person=await authorize(db,identity,lock)
    attempt=await repo.owned_attempt(db,attempt_id,person.id,lock)
    if attempt is None:raise AttemptError('subject',404)
    if attempt.status=='active' and utc(attempt.deadline_at)<=await now(db):
        attempt.status='expired';attempt.submitted_at=attempt.deadline_at;attempt.version+=1
        await repo.save(db)
    return person,attempt


async def save(db, identity, attempt_id, body):
    _,attempt=await owned_attempt(db,identity,attempt_id,True)
    if attempt.status!='active':return dict(status=attempt.status,version=attempt.version)
    if not isinstance(body,dict) or not {'version','responses','submit'}<=set(body) or set(body)-{'version','responses','submit','navigation'} or type(body['version']) is not int or type(body['submit']) is not bool:raise AttemptError('format')
    if body['version']!=attempt.version:raise AttemptError('conflict',409)
    try:responses=validate_responses(body['responses'],attempt.private_data['specs'])
    except (ValueError,TypeError):raise AttemptError('format') from None
    if utc(attempt.deadline_at)<=await now(db):
        attempt.status='expired';attempt.submitted_at=attempt.deadline_at;attempt.version+=1
        await repo.save(db);return dict(status=attempt.status,version=attempt.version)
    navigation=attempt.navigation or {}
    if 'navigation' in body:
        navigation=body['navigation']
        count=len(attempt.presentation)
        if (not isinstance(navigation,dict) or set(navigation)!={'current','flagged'}
            or type(navigation['current']) is not int or not 0<=navigation['current']<count
            or not isinstance(navigation['flagged'],list) or len(navigation['flagged'])>count
            or any(type(n) is not int or not 0<=n<count for n in navigation['flagged'])
            or len(set(navigation['flagged']))!=len(navigation['flagged'])):
            raise AttemptError('format')
    attempt.navigation=navigation
    # Empty/partial answers are valid; only the pupil decides to submit early.
    attempt.responses=responses;attempt.version+=1
    if body['submit']:
        attempt.status='submitted';attempt.submitted_at=await now(db)
    await repo.save(db)
    return dict(status=attempt.status,version=attempt.version)
