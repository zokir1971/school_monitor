"""Normalize explicit work type before legacy DTO parsing; keep all repeated fields."""
from starlette.datastructures import FormData

def normalize_manual_form(form):
    kind=str(form.get('assessment_type') or 'diagnostic')
    mode=str(form.get('assessment_mode') or 'without_objectives')
    values={}
    if kind in ('sor','soch'):
        values.update(assessment_type='summative',assessment_mode={'sor':'assessment_by_section','soch':'assessment_by_quarter'}[kind])
    elif kind=='baseline':
        if mode not in ('without_objectives','by_objectives'):raise ValueError('Выберите общий балл или баллы по целям. / Жалпы балды немесе мақсаттар бойынша балдарды таңдаңыз.')
        values.update(naming_quarter='',section_number='')
    elif mode in ('assessment_by_section','assessment_by_quarter'):
        # Backward-compatible saved form; mode still unambiguously specifies SOR/SOCH.
        pass
    elif mode not in ('without_objectives','by_objectives'):
        raise ValueError('Неизвестный способ ввода результатов. / Нәтиже енгізу тәсілі белгісіз.')
    return FormData([(k,v) for k,v in form.multi_items() if k not in values]+list(values.items()))
