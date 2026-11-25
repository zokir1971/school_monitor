"""Class assignment versions and coverage; no SQL or writes."""
import hashlib
import json

class ClassAssignmentConflict(ValueError):
    pass

def assignment_version(school_class,year,offers,groups,assignments):
    selected=sorted((o for o in offers if o.school_class_id==school_class.id and o.is_active),key=lambda o:o.id)
    ids={o.id for o in selected}
    payload=dict(class_id=school_class.id,school_id=school_class.school_id,year=year,
        active=school_class.is_active,language=school_class.instruction_language,track=school_class.education_track,
        offers=[(o.id,o.subject_id,o.rule_id,o.split_enabled)for o in selected],
        groups=sorted((g.id,g.class_subject_id,g.number)for g in groups if g.class_subject_id in ids and g.is_active),
        assignments=sorted((a.id,a.subject_id,a.subgroup_id or 0,a.staff_member_id or 0,a.is_primary,
                            str(a.unassigned_at or ''))for a in assignments if a.school_class_id==school_class.id and a.is_active))
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def coverage(rows,teacher_ids):
    total=0;assigned=0;missing=[]
    for row in rows:
        offer=row['offer'];subject=row['subject']
        targets=[(None,row['assignment'])]
        if offer.split_enabled:
            by_number={entry['group'].number:entry for entry in row['groups']}
            targets=[(number,by_number[number]['assignment']if number in by_number else None)for number in (1,2)]
        for number,assignment in targets:
            total+=1
            valid=bool(assignment and assignment.is_active and assignment.is_primary
                and assignment.unassigned_at is None and assignment.staff_member_id in teacher_ids)
            if valid:assigned+=1
            else:missing.append(dict(offer_id=offer.id,subject_id=offer.subject_id,
                name_ru=(subject.name_ru or subject.name_kz)if subject else f'Предмет №{offer.subject_id}',
                name_kz=subject.name_kz if subject else f'Пән №{offer.subject_id}',subgroup_number=number))
    return dict(total=total,assigned=assigned,missing_count=len(missing),missing=missing)
