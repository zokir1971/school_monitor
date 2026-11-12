"""Standard instructions are UI text; custom authored directions remain content."""
import re
from app.core.i18n import translate

DEFAULTS = {'single_choice': 'Выберите один правильный ответ.', 'multiple_choice': 'Выберите все правильные ответы.', 'image_choice': 'Выберите правильное изображение.', 'number': 'Введите числовой ответ.', 'short_text': 'Введите краткий ответ.', 'true_false': 'Определите, верно или неверно каждое утверждение.', 'matching': 'Установите соответствие.', 'ordering': 'Расположите элементы в правильном порядке.', 'fill_gaps': 'Заполните пропуски.', 'formula': 'Введите формулу.', 'manual_review': 'Запишите развёрнутый ответ.'}
PAIRS = [('Выберите один правильный ответ.', 'Бір дұрыс жауапты таңдаңыз.'), ('Выберите все правильные ответы.', 'Барлық дұрыс жауаптарды таңдаңыз.'), ('Выберите правильное изображение.', 'Дұрыс суретті таңдаңыз.'), ('Введите числовой ответ.', 'Сандық жауапты енгізіңіз.'), ('Введите краткий ответ.', 'Қысқа жауапты енгізіңіз.'), ('Определите, верно или неверно каждое утверждение.', 'Әр тұжырымның дұрыс немесе бұрыс екенін анықтаңыз.'), ('Установите соответствие.', 'Сәйкестікті орнатыңыз.'), ('Расположите элементы в правильном порядке.', 'Элементтерді дұрыс ретпен орналастырыңыз.'), ('Заполните пропуски.', 'Бос орындарды толтырыңыз.'), ('Введите формулу.', 'Формуланы енгізіңіз.'), ('Запишите развёрнутый ответ.', 'Толық жауап жазыңыз.')]
ALIASES = {
    'Выберите правильный ответ': 'single_choice',
    'Бір дұрыс жауапты таңдаңыз': 'single_choice',
    'Выберите несколько правильных ответов': 'multiple_choice',
    'Бірнеше дұрыс жауапты таңдаңыз': 'multiple_choice',
    'Введите ответ числом': 'number',
    'Жауапты санмен енгізіңіз': 'number',
    'Сопоставьте элементы': 'matching',
    'Сәйкестендіріңіз': 'matching',
    'Определите правильный порядок': 'ordering',
    'Дұрыс ретті анықтаңыз': 'ordering',
    'Заполните пропуски в тексте': 'fill_gaps',
    'Мәтіндегі бос орындарды толтырыңыз': 'fill_gaps',
    'Дұрыс/бұрыс екенін анықтаңыз': 'true_false',
    'Определите, верно или неверно утверждение': 'true_false',
    'Введите ответ': 'short_text',
    'Жауапты енгізіңіз': 'short_text',
    'Дайте развёрнутый ответ': 'manual_review',
    'Развернутый ответ': 'manual_review',
    'Толық жауап беріңіз': 'manual_review',
}

def normalize(value):
    return re.sub(r'\s+', ' ', value.strip()).rstrip('.!').casefold()

KNOWN = {normalize(text): ru for ru, kk in PAIRS for text in (ru, kk)}
KNOWN.update({normalize(alias): DEFAULTS[kind] for alias, kind in ALIASES.items()})

def instruction_text(value, language):
    if not isinstance(value, str) or not value.strip():
        return value or ''
    canonical = KNOWN.get(normalize(value))
    return translate(canonical, language) if canonical else value
