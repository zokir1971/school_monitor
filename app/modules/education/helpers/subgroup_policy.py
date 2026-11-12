"""Deterministic distribution independent of SQL and UI."""
LANGUAGES = {'kz': 'Қазақша', 'ru': 'Русский', 'uz': 'Узбекский', 'tg': 'Таджикский', 'ug': 'Уйгурский'}
LANGUAGE_ALIASES = {'казахский': 'kz', 'қазақ': 'kz', 'қазақша': 'kz', 'русский': 'ru', 'орыс': 'ru', 'узбекский': 'uz',
                    'өзбек': 'uz', 'таджикский': 'tg', 'тәжік': 'tg', 'уйгурский': 'ug', 'ұйғыр': 'ug'}


def infer_language(labels):
    normalized = [' '.join(str(s).strip().casefold().split()) for s in labels]
    codes = {LANGUAGE_ALIASES.get(s.removesuffix(' язык').removesuffix(' тілі'), s) for s in normalized}
    return next(iter(codes)) if len(codes) == 1 and next(iter(codes)) in LANGUAGES else None


def distribute(students, previous):
    """Alphabetical first split; keep prior membership, move the fewest to balance."""
    ordered = sorted(students, key=lambda s: (
        (s.last_name or '').casefold(), (s.first_name or '').casefold(), (s.middle_name or '').casefold(), s.id))
    ids = {s.id for s in ordered}
    result = {sid: n for sid, n in previous.items() if sid in ids and n in (1, 2)}
    if not result:
        limit = (len(ordered) + 1) // 2
        return {s.id: 1 if i < limit else 2 for i, s in enumerate(ordered)}
    counts = {n: sum(v == n for v in result.values()) for n in (1, 2)}
    for s in ordered:
        if s.id not in result:
            n = 1 if counts[1] <= counts[2] else 2
            result[s.id] = n
            counts[n] += 1
    while abs(counts[1] - counts[2]) > 1:
        source = 1 if counts[1] > counts[2] else 2
        target = 3 - source
        sid = next(s.id for s in reversed(ordered) if result[s.id] == source)
        result[sid] = target
        counts[source] -= 1
        counts[target] += 1
    return result
