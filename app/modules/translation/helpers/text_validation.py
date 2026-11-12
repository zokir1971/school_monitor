from app.modules.translation.schemas import TranslationRequest

def validate_request(request: TranslationRequest) -> None:
    if request.language not in {'ru', 'kk'}:
        raise ValueError('Поддерживаются русский и казахский языки.')
    if not request.fields or len({f.key for f in request.fields}) != len(request.fields):
        raise ValueError('Поля перевода должны иметь уникальные ключи.')
    if any(not isinstance(f.text, str) or not f.key for f in request.fields):
        raise ValueError('Некорректные поля перевода.')
    if sum(len(f.text) for f in request.fields) > 40000:
        raise ValueError('Текст слишком велик для одного запроса перевода.')

def validate_result(request: TranslationRequest, result: object) -> dict[str, str]:
    if not isinstance(result, dict) or set(result) != {f.key for f in request.fields}:
        raise ValueError('AI вернул неполный перевод.')
    if any(not isinstance(result[f.key], str) or (not result[f.key].strip() and not f.allow_empty) for f in request.fields):
        raise ValueError('AI вернул неполный перевод.')
    return dict(result)
