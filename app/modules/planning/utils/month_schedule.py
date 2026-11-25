"""Monthly eligibility uses user-selected period fields, never template deadlines."""
import re
from app.modules.planning.constants import ACADEMIC_MONTHS
from app.modules.planning.utils.month_plan_utils import quarter_of_month,previous_months_in_quarter

def code(value):return getattr(value,'value',value)
def field(row,key):return row.get(key)if hasattr(row,'get')else getattr(row,key,None)
def integers(value):return {int(v)for v in re.findall(r'\d+',str('' if value is None else value))}
def period_matches(row,month):
    if field(row,'is_excluded') or month not in ACADEMIC_MONTHS:return False
    kind=code(field(row,'period_type'))
    if kind in ('all_year','monthly'):return True
    if kind=='month':
        try:return int(field(row,'period_value_int'))==month
        except (TypeError,ValueError):return False
    if kind=='months':return month in integers(field(row,'period_values'))
    if kind=='quarter':
        quarter=quarter_of_month(month);selected=integers(field(row,'period_value_int'))
        return quarter is not None and (not selected or quarter in selected)
    return False

class MonthSchedule:
    @staticmethod
    async def evaluate(db,data):
        from app.modules.planning.repositories.month_plan_repository import SchoolMonthlyPlanRepo as Repo
        if not data:return dict(visible_ids=set(),eligible_ids=set(),warning_ids=set(),hidden_ids=set())
        plan=data['plan'];items=data['items'];all_ids={i['id']for i in items}
        sources=await Repo.schedule_periods(db,school_plan_id=plan['school_plan_id'],source_ids={i['source_row11_id']for i in items if i['source_row11_id']is not None})
        excluded={item['id'] for item in items if item.get('annual_exclusion_was_included') is not None
                  or field(sources.get(item['source_row11_id']), 'is_excluded')}
        if code(plan['status'])=='archived' or code(plan.get('annual_status'))=='archived':
            return dict(visible_ids=all_ids-excluded,eligible_ids=all_ids-excluded,warning_ids=set(),hidden_ids=excluded,excluded_ids=excluded)
        quarter_ids=[sid for sid,row in sources.items()if code(row['period_type'])=='quarter']
        done=await Repo.list_previously_completed_quarter_source_ids(db,school_plan_id=plan['school_plan_id'],source_row11_ids=quarter_ids,previous_months=previous_months_in_quarter(plan['month']))
        assigned={a['month_item_id']for a in data.get('assignments',[])}
        visible=set();eligible=set();warnings=set()
        for item in items:
            if item['id'] in excluded:continue
            row=sources.get(item['source_row11_id'])
            # Preserve manual/orphaned legacy entries rather than hiding history.
            matches=row is None or (period_matches(row,plan['month'])and item['source_row11_id']not in done)
            if matches:eligible.add(item['id'])
            protected=(item['is_included']or item['id']in assigned or item.get('exclusion_protected')
                       or code(item.get('status'))not in (None,'todo')or item.get('completed_at')or item.get('executed_at')or item.get('responsible_user_id'))
            if matches or protected:visible.add(item['id'])
            if not matches and protected:warnings.add(item['id'])
        return dict(visible_ids=visible,eligible_ids=eligible,warning_ids=warnings,hidden_ids=all_ids-visible,excluded_ids=excluded)
