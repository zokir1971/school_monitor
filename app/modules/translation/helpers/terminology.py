"""Prompt guidance only: never blindly replace words in user text."""
def terminology_instruction(language: str) -> str:
    if language == 'kk':
        return 'Use МІБ for internal school monitoring and бағалау for assessment. '
    return 'Use ВШК for internal school monitoring and оценивание for assessment. '
