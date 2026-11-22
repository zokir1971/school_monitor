"""Process configuration only: no account, role, or stored report changes."""
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings,SettingsConfigDict

class FeatureSettings(BaseSettings):
    ASSESSMENT_ENABLED: bool = True
    SCHOOL_EDUCATION_ENABLED: bool = True
    RESTRICTED_MODULES_SUPERUSER_ONLY: bool = True
    model_config = SettingsConfigDict(env_file=str(Path(__file__).resolve().parents[2]/'.env.features'),
                                     env_file_encoding='utf-8-sig',extra='ignore',case_sensitive=False)

@lru_cache(maxsize=1)
def get_features():return FeatureSettings()

def restricted_modules_allowed(user=None):
    role=user.get('role') if isinstance(user,dict) else getattr(user,'role',None)
    return not get_features().RESTRICTED_MODULES_SUPERUSER_ONLY or getattr(role,'value',role)=='superuser'

def assessment_enabled():return get_features().ASSESSMENT_ENABLED

def school_education_enabled(user=None):
    role=user.get('role') if isinstance(user,dict) else getattr(user,'role',None)
    return get_features().SCHOOL_EDUCATION_ENABLED or getattr(role,'value',role)=='superuser'

def report_enabled(code):
    return assessment_enabled() or getattr(code,'value',code)!='knowledge_quality_table'

def snapshot_has_assessment(snapshot):
    if not isinstance(snapshot,dict):return False
    if snapshot.get('report_code')=='knowledge_quality_table' or snapshot.get('kind')=='vsk_assessment_quality':return True
    if snapshot.get('kind')=='vsk_assessment_summary' or snapshot.get('report_code') in ('class_summary','teacher_analysis'):
        return ('quality' in (snapshot.get('inspection') or {}).get('sections',[])
                or bool(snapshot.get('rows') or snapshot.get('objectives') or snapshot.get('dynamics')))
    if snapshot.get('report_code')=='analytical_reference':
        return any(e.get('code')=='knowledge_quality_table' or (e.get('code') in ('class_summary','teacher_analysis') and bool(e.get('totals')))
                   for e in snapshot.get('entries',[]) if isinstance(e,dict))
    return False
