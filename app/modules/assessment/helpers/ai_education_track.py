"""Explicit upper-secondary track selection; common objectives remain eligible."""
TRACKS = {'general': '', 'emn': 'emn', 'ogn': 'ogn'}


def selected_track(grade_level, value):
    if grade_level in (10, 11):
        if value not in TRACKS:
            raise ValueError('Для 10–11 классов выберите направление обучения.')
        return TRACKS[value]
    if value not in (None, '', 'general'):
        raise ValueError('Направление обучения доступно только для 10–11 классов.')
    return None


def validate_objective_track(objective_track, grade_level, value):
    track = selected_track(grade_level, value)
    if track is not None and objective_track not in ('', track):
        raise ValueError('Учебная цель не соответствует выбранному направлению.')
