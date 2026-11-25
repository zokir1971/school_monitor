"""Deterministic final-reference assembly; no external provider or AI calls."""
import hashlib
import json
from app.modules.reports.services.assessment_report_service import json_value


def fingerprint(entries,version=1):
    if version==1:
        entries=[{k:v for k,v in row.items() if k not in ('conclusion_text','recommendations_text')} for row in entries]
    payload=json.dumps(json_value(entries),ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(payload.encode()).hexdigest()


def task_metadata(context):
    return {key:json_value(context.get(key) or '') for key in ('task_id','topic','goal','control_object','planned_start','planned_end')}


def analysis_text(entries,language):
    ru=language=='ru';lines=[]
    for row in entries:
        title=row['titles'].get(language) or row['code']
        header=f"{title} · {row['target']}"
        if row['state']=='waived':
            lines.append(header+(': освобождено от выполнения.' if ru else ': орындаудан босатылған.'))
            continue
        parts=[header+f" · №{row['document_id']}"]
        if row.get('score') is not None:
            parts.append(('Балл: ' if ru else 'Балл: ')+str(row['score'])+' / '+str(row.get('max_score') if row.get('max_score') is not None else '—'))
        if row.get('finding'):parts.append(row['finding'])
        lines.append('\n'.join(parts))
    # The full evidence table remains authoritative even when the text is long.
    result='\n\n'.join(lines)
    return result if len(result)<=30000 else result[:29800]+ ('\nПолные данные приведены в таблице исходных отчётов.' if ru else '\nТолық деректер бастапқы есептер кестесінде берілген.')


def numbered_source_text(entries,field,language):
    """Each non-empty completed source is one numbered paragraph; no deduplication."""
    blocks=[]
    length=0
    for row in entries:
        content=str(row.get(field) or '').strip()
        if row['state']!='completed' or not content:
            continue
        title=row['titles'].get(language) or row['code']
        block=f"{len(blocks)+1}. {title} · {row['target']} · №{row['document_id']}\n{content}"
        blocks.append(block)
        length+=len(block)+2
        if length>10000:
            # Preserve a detectable overflow: validation reports the field limit.
            return '\n\n'.join(blocks)[:10001]
    return '\n\n'.join(blocks)


def collect_source_texts(entries,language):
    return dict(conclusion=numbered_source_text(entries,'conclusion_text',language),
                recommendations=numbered_source_text(entries,'recommendations_text',language))


def merge_source_texts(params,previous,generated):
    """Refresh previously automatic text; retain manual edits and intentional clearing."""
    result={}
    old_defaults=previous.get('source_text_defaults') or {}
    for field,automatic in generated.items():
        submitted=str(params.get(field,previous.get(field,'')) or '').strip()
        previous_default=old_defaults.get(field)
        untouched=(field in old_defaults and submitted==previous_default)
        empty_first=(field not in old_defaults and not submitted)
        result[field]=automatic if untouched or empty_first else submitted
    return result
