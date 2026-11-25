"""Five regional sheets from a single school-level data cohort."""
from collections import defaultdict
from dataclasses import replace
from decimal import Decimal

from app.core.ui_locale_context import ui_locale
from app.modules.assessment.repositories.regional_export_repo import school_work_rows
from app.modules.assessment.schemas.knowledge_quality_export_schemas import KnowledgeQualityExportDTO, KnowledgeQualityExportRowDTO
from app.modules.assessment.services.knowledge_quality_analytics_service import KnowledgeQualityAnalyticsService
from app.modules.assessment.services.knowledge_quality_calculator import KnowledgeQualityCalculator
from app.modules.education.repositories.subject_repo import SubjectRepo
from app.modules.org.repositories.org_lookup_repo import OrgLookupRepo

COUNTS = ('total_students', 'participated_students', 'absent_students', 'excused_students',
          'not_completed_students', 'grade_5_count', 'grade_4_count', 'grade_3_count', 'grade_2_count')
CHECKPOINTS = {
    'baseline': ('Нулевой контроль', 'Нөлдік бақылау'),
    'quarter_1': ('I четверть', 'I тоқсан'), 'quarter_2': ('II четверть', 'II тоқсан'),
    'quarter_3': ('III четверть', 'III тоқсан'), 'quarter_4': ('IV четверть', 'IV тоқсан'),
    'final': ('Годовой контроль', 'Жылдық бақылау'),
}


def aggregate(items, *, entity_id, entity_name):
    values = {name: sum(getattr(row, name) for row in items) for name in COUNTS}
    score_sum = sum((row.score_sum for row in items), Decimal(0))
    percent_sum = sum((row.percent_sum for row in items), Decimal(0))
    metrics = KnowledgeQualityCalculator.calculate(**values, score_sum=score_sum, percent_sum=percent_sum)
    return replace(items[0], **values, entity_id=entity_id, entity_name=entity_name,
                   score_sum=score_sum, percent_sum=percent_sum, district_name='',
                   average_score=metrics.average_score, average_percent=metrics.average_percent,
                   achievement_percent=metrics.achievement_percent, quality_percent=metrics.quality_percent)


async def build(db, *, region_id, academic_year_start=None, subject_id=None, grade_level=None,
                work_key=None, governance='', checkpoint=''):
    raw = await school_work_rows(db, region_id=region_id, academic_year_start=academic_year_start,
        subject_id=subject_id, grade_level=grade_level, work_key=work_key,
        checkpoint=checkpoint, governance=governance)
    ids = {row[key] for row in raw for key in ('district_id', 'location_district_id') if row[key] is not None}
    names = await OrgLookupRepo.get_district_names_by_ids(db, district_ids=tuple(ids)) if ids else {}
    region_names = await OrgLookupRepo.get_region_names_by_ids(db, region_ids=(region_id,))
    kk = ui_locale.get() == 'kk'
    subject_name = f'ID {subject_id}' if subject_id is not None else None
    if subject_id is not None:
        subjects = await SubjectRepo.get_active_by_ids(db, subject_ids=(subject_id,))
        if subjects:
            subject = subjects[0]
            subject_name = (subject.name_kz if kk else subject.name_ru) or subject.name_kz or f'ID {subject_id}'
    district_schools, regional_schools, all_schools = [], [], []
    districts, school_parts = defaultdict(list), defaultdict(list)
    levels = {}
    for row in raw:
        counts = {name: int(row[name] or 0) for name in COUNTS}
        metrics = KnowledgeQualityCalculator.calculate(**counts, score_sum=row['score_sum'], percent_sum=row['percent_sum'])
        number = int(row['logical_id'])
        key = ('d:' + str(number)) if number > 0 else ('a:' + str(-number))
        suffix = f'Сессия №{row["session_id"]}' if number > 0 else ('Жұмыс №' if kk else 'Работа №') + str(-number)
        full_title = (row['work_title'] or '—') + ' · ' + suffix
        label = CHECKPOINTS.get(row['checkpoint'])
        item = KnowledgeQualityExportRowDTO(**counts, entity_id=row['school_id'], entity_name=row['school_name'],
            district_name=names.get(row['location_district_id'], f'ID {row["location_district_id"]}'),
            work_key=key, full_work_title=full_title, work_title=label[1 if kk else 0] if label else full_title,
            score_sum=row['score_sum'], percent_sum=row['percent_sum'],
            average_score=metrics.average_score, average_percent=metrics.average_percent,
            achievement_percent=metrics.achievement_percent, quality_percent=metrics.quality_percent)
        school_parts[(key, row['school_id'])].append(item)
        levels[row['school_id']] = row['governance_level']
        if row['governance_level'] == 'district':
            districts[(key, row['district_id'])].append(item)
    for (_, school_id), parts in school_parts.items():
        item = parts[0] if len(parts) == 1 else replace(aggregate(parts, entity_id=school_id, entity_name=parts[0].entity_name), district_name=parts[0].district_name)
        all_schools.append(item)
        (regional_schools if levels[school_id] == 'region' else district_schools).append(item)
    district_rows = tuple(aggregate(items, entity_id=did, entity_name=names.get(did, f'ID {did}'))
                          for (_, did), items in districts.items())
    summaries = KnowledgeQualityAnalyticsService.summarize_work_rows(all_schools)
    direct = {item.work_key: item for item in KnowledgeQualityAnalyticsService.summarize_work_rows(regional_schools)}
    # Keep every selected work visible in the regional-school summary, including
    # zero participants, without inventing an assessment or combining works.
    zero = {name: 0 for name in COUNTS}
    direct_summaries = tuple(direct.get(item.work_key) or replace(item, **zero, entity_name='0',
        score_sum=Decimal(0), percent_sum=Decimal(0), average_score=None, average_percent=None,
        achievement_percent=None, quality_percent=None) for item in summaries)
    return KnowledgeQualityExportDTO(scope='region', title='Региональная аналитика качества знаний',
        organization_id=region_id, organization_name=region_names.get(region_id, f'ID {region_id}'),
        academic_year_start=academic_year_start, subject_id=subject_id, subject_name=subject_name,
        grade_level=grade_level, rows=district_rows, work_summaries=summaries,
        school_rows=tuple(district_schools), regional_rows=tuple(regional_schools),
        regional_work_summaries=direct_summaries, regional_layout=True,
        governance=governance, all_works=work_key in (None, 'all'))
