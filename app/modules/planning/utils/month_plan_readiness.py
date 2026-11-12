"""Pure readiness/deletion checks over the existing batched monthly snapshot."""
def enum_value(value):
    return getattr(value, 'value', value)


def month_plan_readiness(data, weeks):
    if not data:
        return dict(problems=[], included=0, ready=0, can_delete=False, unpublished=[])
    available = {w.week for w in weeks}
    primaries = {a['month_item_id'] for a in data['assignments'] if enum_value(a['assignment_kind']) == 'primary'}
    problems = []
    included = [i for i in data['items'] if i['is_included']]
    for item in included:
        issues = []
        if item['week_of_month'] not in available:
            issues.append('week')
        if item['id'] not in primaries:
            issues.append('primary')
        if issues:
            problems.append(dict(id=item['id'], issues=issues))
    protected = bool(data['assignments'] or data['plan'].get('has_notifications'))
    protected = protected or any(
        i.get('exclusion_protected') or enum_value(i.get('status')) not in (None, 'todo')
        or i.get('week_of_month') is not None or i.get('planned_start') or i.get('planned_end')
        or i.get('notes') or i.get('responsible_user_id') or i.get('completed_at') or i.get('executed_at')
        for i in data['items'])
    can_delete = (enum_value(data['plan']['status']) == 'draft'
        and enum_value(data['plan']['annual_status']) != 'archived' and not protected)
    assigned_ids = {a['month_item_id'] for a in data['assignments']}
    unpublished = [i['id'] for i in data['items'] if not i['is_included'] and (i['id'] in assigned_ids or i.get('week_of_month') is not None)]
    return dict(problems=problems, included=len(included), ready=len(included)-len(problems), can_delete=can_delete, unpublished=unpublished)
