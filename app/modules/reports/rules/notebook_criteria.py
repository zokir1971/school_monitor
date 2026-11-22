"""One bilingual catalogue for standard notebook reports and template defaults."""
from copy import deepcopy


def criterion(key, ru, kk, descriptions):
    return dict(key=key, label_ru=ru, label_kz=kk,
                scores={str(i): dict(label_ru=r, label_kz=k) for i, (r, k) in enumerate(descriptions)})


CHECKING_NOTEBOOKS_CRITERIA = [
    criterion('criterion_0', 'Полнота наличия тетрадей', 'Дәптерлердің толық болуы', [
        ('Тетради отсутствуют у проверенных учеников', 'Тексерілген оқушыларда дәптер жоқ'),
        ('Тетради есть у части проверенных учеников', 'Тексерілген оқушылардың бір бөлігінде дәптер бар'),
        ('Тетради есть у всех проверенных учеников', 'Тексерілген оқушылардың барлығында дәптер бар')]),
    criterion('criterion_1', 'Оформление тетради', 'Дәптердің рәсімделуі', [
        ('Требования не соблюдены', 'Талаптар сақталмаған'),
        ('Есть отдельные нарушения', 'Жекелеген бұзушылықтар бар'),
        ('Аккуратно, требования соблюдены', 'Ұқыпты, талаптар сақталған')]),
    criterion('criterion_2', 'Систематичность письменных работ', 'Жазба жұмыстарының жүйелілігі', [
        ('Письменные работы систематически пропускаются', 'Жазба жұмыстары жүйелі түрде орындалмайды'),
        ('Есть отдельные пропуски письменных работ', 'Кейбір жазба жұмыстары орындалмаған'),
        ('Письменные работы выполняются систематически', 'Жазба жұмыстары жүйелі орындалады')]),
    criterion('criterion_3', 'Выполнение домашнего задания', 'Үй тапсырмасының орындалуы', [
        ('Не выполняет', 'Орындамайды'), ('Выполняет частично', 'Ішінара орындайды'),
        ('Выполняет полностью', 'Толық орындайды')]),
    criterion('criterion_4', 'Систематичность проверки учителем', 'Мұғалімнің тексеруінің жүйелігі', [
        ('Не проверяется', 'Тексерілмейді'), ('Проверяется нерегулярно', 'Жүйесіз тексеріледі'),
        ('Проверяется регулярно', 'Жүйелі түрде тексеріледі')]),
    criterion('criterion_5', 'Качество проверки учителем', 'Мұғалімнің тексеру сапасы', [
        ('Проверка формальная, ошибки не выявляются', 'Тексеру формалды, қателер анықталмайды'),
        ('Выявляется только часть ошибок, обратная связь неполная', 'Қателердің бір бөлігі ғана анықталады, кері байланыс толық емес'),
        ('Ошибки выявляются, даётся понятная обратная связь', 'Қателер анықталады, түсінікті кері байланыс беріледі')]),
    criterion('criterion_6', 'Работа над ошибками', 'Қателермен жұмыс жүргізілуі', [
        ('Не выполняется', 'Орындалмайды'), ('Выполняется частично', 'Ішінара орындалады'),
        ('Выполняется', 'Орындалады')]),
    criterion('criterion_7', 'Каллиграфия и соблюдение требований к записям', 'Көркем жазу және талапқа сай рәсімделуі', [
        ('Записи неразборчивы, требования не соблюдены', 'Жазу түсініксіз, талаптар сақталмаған'),
        ('Есть отдельные нарушения почерка и оформления', 'Жазу мен рәсімдеуде жекелеген кемшіліктер бар'),
        ('Записи разборчивы, требования соблюдены', 'Жазу анық, талаптар сақталған')]),
    criterion('criterion_8', 'Грамотность', 'Сауаттылық', [
        ('Много ошибок', 'Қателер көп'), ('Есть отдельные ошибки', 'Жекелеген қателер бар'),
        ('Без ошибок', 'Қатесіз')]),
]

CHECKING_NOTEBOOKS_RATING = dict(max_score_per_criterion=2, levels=[
    {'from':90, 'to':100, 'label_ru':'Высокий', 'label_kz':'Жоғары'},
    {'from':70, 'to':89, 'label_ru':'Достаточный', 'label_kz':'Жеткілікті'},
    {'from':50, 'to':69, 'label_ru':'Средний', 'label_kz':'Орташа'},
    {'from':0, 'to':49, 'label_ru':'Низкий', 'label_kz':'Төмен'},
])

_ALIASES = {'exists':0, 'design':1, 'homework':3, 'literacy':8, 'teacher_check':4, 'correction':6}
_OLD_LABELS = {0:{'Наличие тетради','Дәптердің болуы'}, 4:{'Проверка учителем','Мұғалімнің тексеруі'}, 6:{'Қатемен жұмыс'}}


def with_notebook_rubrics(schema):
    """Enrich known legacy criteria without changing keys, order, scales or count.

    Custom labels/scores and stored document versions remain authoritative.
    No input dictionary is mutated; GET never updates a document in the DB.
    """
    result = deepcopy(schema or {})
    if not result:
        return result
    scale = result.get('score_scale') or [0, 1, 2]
    for index, item in enumerate(result.get('criteria') or []):
        if not isinstance(item, dict):
            continue
        key = str(item.get('key') or f'criterion_{index}')
        candidate = _ALIASES.get(key)
        if candidate is None and key.startswith('criterion_') and key[10:].isdigit():
            candidate = int(key[10:])
        if candidate is None or not 0 <= candidate < len(CHECKING_NOTEBOOKS_CRITERIA):
            continue
        source = CHECKING_NOTEBOOKS_CRITERIA[candidate]
        known = {source['label_ru'], source['label_kz']} | _OLD_LABELS.get(candidate, set())
        labels = {item.get(k) for k in ('label_ru','label_kz','text','name') if item.get(k)}
        if not labels or not labels.issubset(known):
            continue
        item.setdefault('label_ru', source['label_ru'])
        item.setdefault('label_kz', source['label_kz'])
        if not item.get('scores') and {str(v) for v in scale} == {'0','1','2'}:
            item['scores'] = deepcopy(source['scores'])
    rating = result.get('rating') or {}
    if not rating.get('levels'):
        rating['levels'] = deepcopy(CHECKING_NOTEBOOKS_RATING['levels'])
    rating.setdefault('max_score_per_criterion', 2)
    result['rating'] = rating
    return result
