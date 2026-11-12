"""Pure bilingual naming. Frozen names live in existing settings/title fields."""
from app.core.ui_locale_context import ui_locale
VERSION='standard_name_v1'
def code(v):return getattr(v,'value',v)
def names(*,kind,subject_kk,subject_ru,grades,year,quarter=None,track=None,number=None):
    kind=code(kind);grades=sorted(set(int(g) for g in grades))
    if not grades or any(g<1 or g>12 for g in grades):raise ValueError('Проверьте класс. / Сыныпты тексеріңіз.')
    if not 2000<=int(year)<=2100:raise ValueError('Проверьте учебный год. / Оқу жылын тексеріңіз.')
    if kind in ('sor','soch') and quarter not in (1,2,3,4):raise ValueError('Выберите четверть. / Тоқсанды таңдаңыз.')
    if number is not None and (kind!='sor' or not 1<=int(number)<=99):raise ValueError('Проверьте номер СОР. / БЖБ нөмірін тексеріңіз.')
    labels={'baseline':('Нөлдік бақылау','Нулевой контроль'),'sor':('БЖБ','СОР'),'soch':('ТЖБ','СОЧ'),
      'diagnostic':('Диагностикалық жұмыс','Диагностическая работа'),'monitoring':('Мониторингтік жұмыс','Мониторинговая работа'),
      'control':('Бақылау жұмысы','Контрольная работа'),'summative':('Жиынтық бағалау','Суммативное оценивание'),'custom':('Бағалау жұмысы','Оценочная работа')}
    if kind not in labels:raise ValueError('Неизвестный тип работы. / Жұмыс түрі белгісіз.')
    result={};roman={1:'I',2:'II',3:'III',4:'IV'}
    for lang,index,subject in [('kk',0,subject_kk),('ru',1,subject_ru or subject_kk)]:
        heading=labels[kind][index]+(f' №{int(number)}' if number else '')
        parts=[heading]
        if quarter and kind!='baseline':parts.append(roman[quarter]+(' тоқсан' if lang=='kk' else ' четверть'))
        parts.append(' '.join(str(subject or '').split()) or ('Пән' if lang=='kk' else 'Предмет'))
        parts.append(', '.join(map(str,grades))+(' сынып' if lang=='kk' else ' класс'))
        direction={'emn':('ЖМБ','ЕМН'),'ogn':('ҚГБ','ОГН')}.get(track)
        if direction:parts.append(direction[index])
        parts.append(f'{year}–{int(year)+1}')
        # Keep every parameter; shorten only an exceptionally long subject label.
        title=' · '.join(parts)
        if len(title)>255:
            pos=2 if quarter and kind!='baseline' else 1
            room=255-(len(title)-len(parts[pos]));parts[pos]=parts[pos][:max(0,room-1)]+'…'
            title=' · '.join(parts)
        if len(title)>255:raise ValueError('Название слишком длинное. / Атау тым ұзын.')
        result[lang]=title
    return result

def localized(assessment,language=None):
    saved=(getattr(assessment,'settings',None) or {}).get(VERSION) or {}
    return saved.get(language or ui_locale.get()) or assessment.title

def manual_names(dto,subject,classes):
    years={c.academic_year_start for c in classes};grades={c.grade_level for c in classes}
    if len(years)!=1:raise ValueError('Выберите классы одного учебного года. / Бір оқу жылының сыныптарын таңдаңыз.')
    checkpoint=code(dto.checkpoint);mode=code(dto.assessment_mode)
    kind='baseline' if code(dto.assessment_type)=='baseline' else {'assessment_by_section':'sor','assessment_by_quarter':'soch'}.get(mode,code(dto.assessment_type))
    quarter=dto.quarter
    if kind=='baseline':
        quarter=None
        if checkpoint not in (None,'baseline'):raise ValueError('Нулевой контроль несовместим с четвертной точкой. / Нөлдік бақылауға тоқсандық нүкте сәйкес емес.')
    elif checkpoint=='baseline':raise ValueError('Для этой точки выберите тип «Нулевой контроль». / Бұл нүкте үшін «Нөлдік бақылау» түрін таңдаңыз.')
    elif checkpoint and checkpoint.startswith('quarter_') and quarter!=int(checkpoint[-1]):
        raise ValueError('Четверть и контрольная точка не совпадают. / Тоқсан мен бақылау нүктесі сәйкес емес.')
    tracks={getattr(c,'education_track',None) for c in classes}-{None,'','general'}
    if len(tracks)>1:raise ValueError('Выберите классы одного направления. / Бір бағыттағы сыныптарды таңдаңыз.')
    if kind=='baseline' and mode not in ('without_objectives','by_objectives'):raise ValueError('Выберите общий балл или баллы по целям. / Жалпы балды немесе мақсаттар бойынша балдарды таңдаңыз.')
    if kind=='baseline' and min(grades)<2:raise ValueError('Нулевой контроль доступен со 2 класса. / Нөлдік бақылау 2-сыныптан бастап қолжетімді.')
    title=names(kind=kind,subject_kk=subject.name_kz,subject_ru=subject.name_ru,grades=grades,year=next(iter(years)),
       quarter=quarter,track=next(iter(tracks),None),number=dto.section_number if kind=='sor' else None)
    return dict(**{VERSION:title},work_type=kind,quarter=quarter,section_number=dto.section_number if kind=='sor' else None,
       academic_year_start=next(iter(years)),participant_grades=sorted(grades),education_track=next(iter(tracks),None),
       curriculum_grades=sorted(g-1 for g in grades) if kind=='baseline' else sorted(grades))

def subject_title(subject,language):
    context=subject.get('assessment_context') if isinstance(subject,dict) else getattr(subject,'assessment_context',None)
    saved=(context or {}).get(VERSION) or {}
    name=subject.get('name_'+language) if isinstance(subject,dict) else getattr(subject,'name_'+language,None)
    return saved.get(language) or name or ''
