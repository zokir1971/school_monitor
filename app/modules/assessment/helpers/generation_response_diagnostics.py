"""Small safe metadata snapshot and an early response-shape check."""


def response_metadata(response):
    def field(node, name):
        return node.get(name) if isinstance(node, dict) else getattr(node, name, None)

    result = {}
    for name in ('id', 'status', 'model'):
        value = field(response, name)
        if isinstance(value, str):
            result[name] = value[:200]
    details = field(response, 'incomplete_details')
    reason = field(details, 'reason')
    if isinstance(reason, str):
        result['incomplete_reason'] = reason[:200]
    usage = field(response, 'usage')
    result['usage'] = {name: field(usage, name) for name in
                       ('input_tokens', 'output_tokens', 'total_tokens')
                       if type(field(usage, name)) is int}
    return result


def validate_response_envelope(payload, expected_count):
    if not isinstance(payload, dict):
        raise ValueError('AI response must be an object.')
    questions = payload.get('questions')
    if not isinstance(questions, list):
        raise ValueError('AI response questions must be an array.')
    for index, question in enumerate(questions, 1):
        if not isinstance(question, dict):
            raise ValueError(
                f'AI question #{index} must be an object, got {type(question).__name__}. '
                f'Requested {expected_count} questions; response contains {len(questions)} elements.')
    if len(questions) != expected_count:
        raise ValueError(f'AI returned {len(questions)} questions; requested {expected_count}.')
