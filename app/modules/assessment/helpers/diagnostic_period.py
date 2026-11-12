"""Calendar input is explicitly local UTC+5; DB timestamps are UTC-aware."""
from datetime import datetime,timedelta,timezone
from app.modules.assessment.helpers.work_plan_rules import WorkPlanError
LOCAL=timezone(timedelta(hours=5),'UTC+5')


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def local_input(value):
    return utc(value).astimezone(LOCAL).strftime('%Y-%m-%dT%H:%M') if value else ''


def display(value):
    return utc(value).astimezone(LOCAL).strftime('%d.%m.%Y %H:%M') if value else '—'


def parse_period(values,now):
    try:
        values=[str(values.get(k,'')).strip() for k in ('opens_at','closes_at')]
        if any(not v or len(v)>40 for v in values):raise ValueError()
        dates=[datetime.fromisoformat(v) for v in values]
        if any(d.tzinfo is not None for d in dates):raise ValueError()
        start,end=[d.replace(tzinfo=LOCAL).astimezone(timezone.utc) for d in dates]
        if end<=start or end<=utc(now):raise ValueError()
    except (ValueError,TypeError,OverflowError) as exc:
        raise WorkPlanError('Укажите начало и окончание периода: окончание должно быть позже начала и текущего времени. / Кезеңнің басталуы мен аяқталуын көрсетіңіз: аяқталуы басталуынан және ағымдағы уақыттан кейін болуы керек.') from exc
    return start,end


def start_block(session,now,minutes):
    if session.opens_at is not None and utc(now)<utc(session.opens_at):return 'not_open'
    if session.closes_at is not None:
        end=utc(session.closes_at)
        if utc(now)>=end:return 'period_closed'
        if utc(now)+timedelta(minutes=minutes)>end:return 'insufficient'
    return None
