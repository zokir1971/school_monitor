# app/models/staff/utils/csv_tools.py (импорт персонала из файла .csv НОБД)

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime


def normalize_header(h: str) -> str:
    """
    Приводит заголовок колонки к стабильному виду:
    - lower + strip
    - убирает BOM
    - заменяет NBSP
    - убирает [1234] и [slug]
    - убирает '*'
    - схлопывает пробелы
    """
    h = (h or "").replace("\ufeff", "").replace("\xa0", " ").strip().lower()

    # убрать маркеры в квадратных скобках: [7303], [teacher_diploma], [order_hire]
    h = re.sub(r"\[\s*[^]]+\s*]", "", h)

    # убрать звездочки (часто в "Ведет предмет ...*")
    h = h.replace("*", "")

    # привести разделители к пробелу (чтобы contains работал стабильнее)
    h = h.replace("/", " ")

    # убрать повторяющиеся пробелы
    h = re.sub(r"\s+", " ", h).strip()

    return h


def get_value(row: dict[str, str], *candidates: str, contains: list[str] | None = None) -> str | None:
    """
    Берет значение из row по:
    - точным именам candidates
    - нормализованным именам
    - (опц.) по contains: список ключевых слов, которые должны входить в заголовок
    """
    # 1) точные ключи
    for c in candidates:
        if c in row:
            return row.get(c)

    # 2) нормализованные ключи
    norm_map = {normalize_header(k): k for k in row.keys()}
    for c in candidates:
        ck = normalize_header(c)
        if ck in norm_map:
            return row.get(norm_map[ck])

    # 3) поиск по contains
    if contains:
        for k in row.keys():
            nk = normalize_header(k)
            if all(word in nk for word in contains):
                return row.get(k)

    return None


def parse_date(value: str | None) -> date | None:
    s = (value or "").strip()
    if not s:
        return None

    # ISO: YYYY-MM-DD
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass

    # DD.MM.YYYY
    try:
        return datetime.strptime(s, "%d.%m.%Y").date()
    except ValueError:
        return None


def parse_int(value: str | None) -> int | None:
    s = (value or "").strip()
    if not s:
        return None

    m = re.search(r"\d+", s.replace(",", "."))
    if not m:
        return None

    try:
        return int(m.group(0))
    except ValueError:
        return None


def safe_str(value: str | None) -> str | None:
    s = (value or "").strip()
    return s or None


def decode_bytes(raw: bytes) -> str:
    # UTF-16 BOM
    if raw.startswith(b'\xff\xfe') or raw.startswith(b'\xfe\xff'):
        return raw.decode("utf-16")
    # UTF-8 BOM
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw.decode("utf-8-sig")
    # обычный UTF-8
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # fallback
        return raw.decode("cp1251")


def clean_excel_cell(v: str | None) -> str:
    """Нормализует значения из Excel/CSV: ="..." -> ..., убирает NBSP, пробелы."""
    if v is None:
        return ""
    s = str(v).strip()
    if s.startswith('="') and s.endswith('"'):
        s = s[2:-1].strip()
    return s.replace("\xa0", " ").strip()


def normalize_iin(v) -> str:
    s = clean_excel_cell(v)
    digits = re.sub(r"\D+", "", s)
    return digits if len(digits) == 12 else ""


def build_full_name(row: dict[str, str]) -> str | None:
    last_name = clean_excel_cell(row.get("Фамилия") or row.get("Жөні"))
    first_name = clean_excel_cell(row.get("Имя") or row.get("Аты"))
    middle_name = clean_excel_cell(row.get("Отчество") or row.get("Әкесінің аты"))

    parts = [p for p in (last_name, first_name, middle_name) if p]
    return " ".join(parts)


def get_iin(row: dict) -> str:
    raw = row.get("ИИН") or row.get("ЖСН")
    if not raw:
        raw = get_value(row, "ИИН", contains=["иин", "жсн", "iin"])
    return normalize_iin(raw)


def map_row_to_fields(row: dict[str, str]) -> dict:
    """
    Маппинг CSV/TSV → поля модели.
    Поддерживает RU + KZ заголовки и заголовки с кодами [xxxx].
    """

    # --- Должность ---
    # RU: "Должность", "Должность [6649]"
    # KZ: "Лауазым", "Лауазым [6649]"
    position_text = safe_str(clean_excel_cell(get_value(
        row,
        "Должность",
        "Должность [6649]",
        "Лауазым",
        "Лауазым [6649]",
        contains=["должн", "лауазым"],
    )))

    # --- Академическая степень ---
    # RU: "Академическая, ученая степень"
    # KZ: "Академиялық, ғылыми дәреже [6798]"
    academic_degree = safe_str(clean_excel_cell(get_value(
        row,
        "Академическая, ученая степень",
        "Академическая степень",
        "Академиялық, ғылыми дәреже",
        "Академиялық, ғылыми дәреже [6798]",
        contains=["академ", "степен", "дәреж"],
    )))

    # --- Образование ---
    # RU: "Образование"
    # KZ: "Білімі [197]"
    education = safe_str(clean_excel_cell(get_value(
        row,
        "Образование",
        "Білімі",
        "Білімі [197]",
        contains=["образован", "білім"],
    )))

    # --- Общий стаж (total) ---
    # RU: "Общий стаж работы на текущий момент"
    # KZ: "Ағымдағы мерзімдегі жалпы еңбек  өтілі [7061]" (или похожие)
    total_experience_years = parse_int(clean_excel_cell(get_value(
        row,
        "Общий  стаж работы на текущий момент",
        "Общий стаж работы на текущий момент",
        "Ағымдағы мерзімдегі жалпы еңбек  өтілі [7061]",
        "Ағымдағы мерзімдегі жалпы еңбек өтілі [7061]",
        contains=["общ", "стаж", "еңбек", "өтіл", "жалпы", "ағымдағы"],
    )))

    # --- Педагогический стаж ---
    # RU: "Стаж педагогической работы на текущий момент"
    # KZ: "Ағымдағы мерзімдегі  педагогикалық еңбек өтілі [7062]"
    ped_experience_years = parse_int(clean_excel_cell(get_value(
        row,
        "Стаж педагогической работы на текущий момент",
        "Ағымдағы мерзімдегі  педагогикалық еңбек өтілі [7062]",
        "Ағымдағы мерзімдегі педагогикалық еңбек өтілі [7062]",
        contains=["пед", "стаж", "педагог", "еңбек", "өтіл"],
    )))

    # --- Категория/Санаты ---
    qualification_category = safe_str(clean_excel_cell(get_value(
        row,
        "Категория",
        "Санаты",
        "Санаты [198]",
        contains=["категор", "санат"],
    )))

    # --- Предмет (основная нагрузка) ---
    # RU: "Ведет предмет (основная нагрузка) [6658]"
    # KZ: "Пәнді жүргізу (негізгі жүктеме) [6658]"
    subject = safe_str(clean_excel_cell(get_value(
        row,
        "Ведет предмет (основная нагрузка)* [6658]",
        "Ведет предмет (основная нагрузка) [6658]",
        "Ведет предмет (основная нагрузка)",
        "Пәнді жүргізу (негізгі жүктеме) [6658]",
        "Пәнді жүргізу (негізгі жүктеме)",
        contains=["ведет", "предмет", "основн", "пән", "негізгі", "жүктеме"],
    )))

    return {
        "position_text": position_text or None,
        "education": education or None,
        "academic_degree": academic_degree or None,
        "subject": subject or None,
        "qualification_category": qualification_category or None,
        "ped_experience_years": ped_experience_years,
        "total_experience_years": total_experience_years,
    }


@dataclass
class CsvReadResult:
    rows: list[dict[str, str]]
    delimiter: str


def read_csv_bytes(raw: bytes) -> CsvReadResult:
    """
    Читает CSV/TSV bytes → list[dict].
    Без Sniffer (он часто ломается на гос-выгрузках).
    Делимитер определяем по КОЛИЧЕСТВУ разделителей в заголовке.
    """
    text = decode_bytes(raw)

    lines = text.splitlines()
    first_line = lines[0] if lines else ""

    # Определяем разделитель надежнее: выбираем тот, которого больше
    counts = {
        "\t": first_line.count("\t"),
        ";": first_line.count(";"),
        ",": first_line.count(","),
        "|": first_line.count("|"),
    }
    delimiter = max(counts, key=counts.get) if max(counts.values()) > 0 else ","

    f = io.StringIO(text, newline="")  # важно для csv
    reader = csv.DictReader(f, delimiter=delimiter)

    rows: list[dict[str, str]] = []
    for row in reader:
        # можно сразу пропускать полностью пустые строки
        if not row:
            continue
        # иногда попадаются строки где все значения пустые
        if all((v is None or str(v).strip() == "") for v in row.values()):
            continue
        rows.append(row)

    return CsvReadResult(rows=rows, delimiter=delimiter)
