"""Read official HTML-XLS, BIFF-XLS and XLSX exports without rewriting them."""

from __future__ import annotations

from collections import defaultdict
from html.parser import HTMLParser
import io
import re
import zipfile
from typing import TypedDict, cast

CODE = re.compile(
    r"(?<![\d.])((?:1[0-2]|[1-9])\s*\.\s*\d+\s*\.\s*\d+\s*\.\s*\d+)(?![\d.])"
)
QUARTER = re.compile(r"(?<!\d)([1-4])(?:\s*[-–—])*\s*(?:тоқсан|четверть)", re.I)
SKILLS = {
    "тыңдалым және айтылым": "listening_speaking",
    "слушание и говорение": "listening_speaking",
    "тыңдалым": "listening",
    "аудирование": "listening",
    "слушание": "listening",
    "айтылым": "speaking",
    "говорение": "speaking",
    "оқылым": "reading",
    "чтение": "reading",
    "жазылым": "writing",
    "письмо": "writing",
    "тілдік нормаларды қолдану": "language_norms",
    "тілдік дағдылар": "language_skills",
    "тілдік дағдыларды қолдану": "language_skills",
    "тілдік дағдыларды дамыту": "language_skills",
    "языковые навыки": "language_skills",
    "применение языковых навыков": "language_skills",
    "тілдік нормалардың қолданысы": "language_norms",
    "әдеби тіл нормалары": "language_norms",
    "нормы литературного языка": "language_norms",
    "соблюдение языковых норм": "language_norms",
    "использование языковых норм": "language_norms",
}
# Formatting characters introduced by official website/Excel exports.
# Normalize only parsing text; source cell provenance retains the original value.
INVISIBLE_FORMATTING = str.maketrans("", "", "\u200b\u200c\u200d\u2060\ufeff\u00ad")

OBJECTIVE_HEADERS = ('оқу мақсаттары', 'оқыту мақсаттары', 'цели обучения', 'учебные цели')


def normalized_header(value: str) -> str:
    return re.sub(r"\s+", " ", value.translate(INVISIBLE_FORMATTING)).casefold().strip(" *")


def is_objective_header(value: str) -> bool:
    # Support bilingual headings and official explanatory suffixes, but require
    # an actual objective-heading phrase at the beginning of a slash component.
    for part in re.split(r"[/|]", normalized_header(value)):
        part = part.strip()
        if any(part == title or part.startswith(
                title + '. ') or part.startswith(title + ': ') for title in OBJECTIVE_HEADERS):
            return True
    return False


def parsing_text(value: str) -> str:
    return value.translate(INVISIBLE_FORMATTING)


MAX_ROWS = 10000
MAX_CELLS = 200000


def clean(value: object) -> str:
    return str(value if value is not None else "").strip()


class ExportHTML(HTMLParser):
    """Expand rowspan/colspan explicitly; no blanket forward-fill of objective cells."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.rows = []
        self.row = None
        self.cell = None
        self.attributes = {}
        self.table_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.table_depth += 1
            if self.table_depth > 1:
                raise ValueError("Вложенные таблицы не поддерживаются.")
            self.rows = []
        elif tag == "tr" and self.table_depth:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
            self.attributes = dict(attrs)
        elif tag == "br" and self.cell is not None:
            self.cell.append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            try:
                rs = int(self.attributes.get("rowspan", "1"))
                cs = int(self.attributes.get("colspan", "1"))
            except ValueError:
                raise ValueError("Неверное объединение ячеек.") from None
            if not 1 <= rs <= MAX_ROWS or not 1 <= cs <= 100:
                raise ValueError("Слишком большое объединение ячеек.")
            self.row.append((clean(" ".join(self.cell)), rs, cs))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
            if len(self.rows) > MAX_ROWS:
                raise ValueError("Слишком много строк.")
        elif tag == "table" and self.table_depth:
            self.tables.append(self.rows)
            self.table_depth = 0


def html_grids(content: bytes):
    parser = ExportHTML()
    try:
        parser.feed(content.decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise ValueError(
            "HTML-XLS должен иметь кодировку UTF-8. Сохраните файл как XLSX в Excel."
        ) from None
    result = []
    for index, rows in enumerate(parser.tables, 1):
        grid = {}
        origins = {}
        for r, cells in enumerate(rows, 1):
            col = 1
            for value, rs, cs in cells:
                while (r, col) in grid:
                    col += 1
                for rr in range(r, r + rs):
                    for cc in range(col, col + cs):
                        if (rr, cc) in grid:
                            raise ValueError("Пересекающиеся объединения ячеек.")
                        grid[rr, cc] = value
                        origins[rr, cc] = (r, col)
                        if len(grid) > MAX_CELLS:
                            raise ValueError("Слишком большая таблица.")
                col += cs
        result.append((f"Table{index}", grid, origins))
    return result


def read_grids(content: bytes):
    if content.startswith(b"PK"):
        from openpyxl import load_workbook

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 64 * 1024 * 1024:
                    raise ValueError("Распакованный XLSX слишком большой.")
            workbook = load_workbook(
                io.BytesIO(content), data_only=False, read_only=False, keep_links=False
            )
        except (zipfile.BadZipFile, KeyError, OSError):
            raise ValueError("Не удалось прочитать XLSX.") from None
        result = []
        try:
            for sheet in workbook:
                if (
                        sheet.max_row > MAX_ROWS
                        or sheet.max_row * sheet.max_column > MAX_CELLS
                ):
                    raise ValueError("Слишком большая таблица.")
                grid = {}
                origins = {}
                for row in sheet:
                    for cell in row:
                        if cell.data_type == "f":
                            raise ValueError(
                                f"{sheet.title}!{cell.coordinate}: формулы не допускаются в исходной выгрузке."
                            )
                        if cell.value is not None:
                            grid[cell.row, cell.column] = clean(cell.value)
                            origins[cell.row, cell.column] = (cell.row, cell.column)
                for merged in sheet.merged_cells.ranges:
                    value = grid.get((merged.min_row, merged.min_col), "")
                    for rr in range(merged.min_row, merged.max_row + 1):
                        for cc in range(merged.min_col, merged.max_col + 1):
                            grid[rr, cc] = value
                            origins[rr, cc] = (merged.min_row, merged.min_col)
                result.append((sheet.title, grid, origins))
        finally:
            workbook.close()
        return result
    if content.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        import xlrd

        try:
            workbook = xlrd.open_workbook(file_contents=content)
        except xlrd.XLRDError:
            raise ValueError(
                "Не удалось прочитать XLS. Сохраните его как XLSX в Excel."
            ) from None
        result = []
        for sheet in workbook.sheets():
            if sheet.nrows > MAX_ROWS or sheet.nrows * sheet.ncols > MAX_CELLS:
                raise ValueError("Слишком большая таблица.")
            grid = {
                (r + 1, c + 1): clean(sheet.cell_value(r, c))
                for r in range(sheet.nrows)
                for c in range(sheet.ncols)
                if sheet.cell_value(r, c) != ""
            }
            origins = {key: key for key in grid}
            # xlrd merged cells require formatting_info; parse only BIFF files which support it.
            detailed = xlrd.open_workbook(
                file_contents=content, formatting_info=True
            ).sheet_by_name(sheet.name)
            for r0, r1, c0, c1 in detailed.merged_cells:
                for rr in range(r0 + 1, r1 + 1):
                    for cc in range(c0 + 1, c1 + 1):
                        grid[rr, cc] = grid.get((r0 + 1, c0 + 1), "")
                        origins[rr, cc] = (r0 + 1, c0 + 1)
            result.append((sheet.name, grid, origins))
        return result
    if b"<table" in content[:8192].lower():
        return html_grids(content)
    raise ValueError(
        "Поддерживаются XLSX, XLS и HTML-таблицы с расширением XLS. PDF загружается отдельно."
    )


def column_name(number):
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


class SourceCell(TypedDict):
    sheet: str
    cell: str
    raw: str


class ParsedObjective(TypedDict):
    code: str
    grade_level: int
    title: str
    quarters: list[int]
    section_title: str
    subsection_title: str
    language_skill: str
    section_code: str
    subsection_code: str
    cells: list[SourceCell]


def extract_table(
    content: bytes,
    *,
    grade: int,
) -> tuple[list[ParsedObjective], list[str]]:
    entries: list[ParsedObjective] = []
    warnings: list[str] = []
    recognized = 0

    for sheet, grid, origins in read_grids(content):
        max_row = max((r for r, _ in grid), default=0)
        max_col = max((c for _, c in grid), default=0)

        columns: dict[str, int | None] | None = None
        quarter: int | None = None
        previous: ParsedObjective | None = None
        seen_origins: set[tuple[int, int]] = set()
        section_context = ""

        for r in range(1, max_row + 1):
            values = [
                grid.get((r, c), "")
                for c in range(1, max_col + 1)
            ]
            header = {
                c: normalized_header(value)
                for c, value in enumerate(values, 1)
            }

            objective_col = next(
                (
                    c
                    for c, value in header.items()
                    if is_objective_header(value)
                ),
                None,
            )

            if objective_col is not None:
                columns = {
                    "objective": objective_col,
                    "section": next(
                        (
                            c
                            for c, value in header.items()
                            if value.startswith(
                                (
                                    "коммуникативтік дағдылар",
                                    "коммуника-тивтік дағдылар",
                                    "коммуника- тивтік дағдылар",
                                    "коммуникативные навыки",
                                    "сөйлеу әрекетінің түрлері",
                                    "сөйлеу әрекеттерінің түрлері",
                                    "виды речевой деятельности",
                                    "тілдік дағдылар",
                                    "языковые навыки",
                                    "тілдік нормалардың қолданысы",
                                    "тақырыптар/ жоспардың мазмұны",
                                    "тақырыптар / жоспардың мазмұны",
                                    "темы/ содержание плана",
                                    "темы / содержание плана",
                                    "бөлім (",
                                    "раздел (",
                                    "ұзақ мерзімді жоспардың бөлімдері",
                                    "ұзақ мерзімді жоспар бөлімі",
                                    "разделы долгосрочного плана",
                                )
                            )
                        ),
                        None,
                    ),
                    "subsection": next(
                        (
                            c
                            for c, value in header.items()
                            if value.startswith(("бөлімше", "подраздел"))
                        ),
                        None,
                    ),
                }
                recognized += 1
                section_context = ""
                previous = None
                continue

            marker = (
                QUARTER.search(" ".join(values))
                if not any(
                    CODE.search(parsing_text(value))
                    for value in values
                )
                else None
            )

            if marker is not None:
                quarter = int(marker[1])
                section_context = ""
                previous = None
                continue

            if columns is None:
                continue

            section_col = columns["section"]
            section_value = grid.get((r, section_col), "") if section_col is not None else ""
            # Some exports split a combined skill across two rows, even when
            # both rows contain objective text. Resolve both before saving either.
            next_section = grid.get((r + 1, section_col), "") if section_col is not None else ""
            combined = section_value + " " + next_section
            if SKILLS.get(normalized_header(combined)) == "listening_speaking":
                section_value = combined
            elif (
                normalized_header(section_value) in ("және айтылым", "и говорение")
                and SKILLS.get(normalized_header(section_context)) == "listening_speaking"
            ):
                section_value = section_context
            if section_value.strip():
                section_context = section_value

            col = columns["objective"]
            if col is None:
                continue

            value = grid.get((r, col), "")
            origin = origins.get((r, col), (r, col))

            if not value or origin in seen_origins:
                continue

            seen_origins.add(origin)
            cell = f"{column_name(col)}{r}"

            location: SourceCell = {
                "sheet": sheet,
                "cell": cell,
                "raw": value,
            }

            value = parsing_text(value)
            matches = list(CODE.finditer(value))

            if not matches:
                if (
                    previous is not None
                    and quarter is not None
                    and quarter in previous["quarters"]
                ):
                    previous["title"] = clean(
                        previous["title"] + " " + value
                    )
                    source_cells = cast(list[SourceCell], previous["cells"])
                    source_cells.append(location)
                    warnings.append(
                        f'{sheet}!{cell}: текст без кода присоединён '
                        f'к {previous["code"]}; проверьте продолжение.'
                    )
                else:
                    warnings.append(
                        f"{sheet}!{cell}: строка без кода "
                        f"не импортирована: {value[:100]}"
                    )
                continue

            if quarter is None:
                raise ValueError(
                    f"{sheet}!{cell}: до цели не найдена четверть."
                )

            section_col = columns["section"]
            subsection_col = columns["subsection"]

            # Official exports may leave repeated section cells blank instead of merging.
            # Carry only the section inside this table/quarter, never objective text.
            section = section_context
            subsection = (
                grid.get((r, subsection_col), "")
                if subsection_col is not None
                else ""
            )

            for i, match in enumerate(matches):
                code = re.sub(r"\s+", "", match[1])

                if int(code.split(".")[0]) != grade:
                    raise ValueError(
                        f"{sheet}!{cell}: код {code} "
                        f"не соответствует выбранному классу {grade}."
                    )

                title_end = (
                    matches[i + 1].start()
                    if i + 1 < len(matches)
                    else len(value)
                )
                title = value[match.end():title_end].strip()

                if title.startswith("*"):
                    title = title[1:].lstrip()

                skill = SKILLS.get(normalized_header(section))

                entry: ParsedObjective = {
                    "code": code,
                    "grade_level": grade,
                    "title": title,
                    "quarters": [quarter],
                    "section_title": section,
                    "subsection_title": subsection,
                    "language_skill": skill or "",
                    "section_code": code.split(".")[1],
                    "subsection_code": ".".join(code.split(".")[1:3]),
                    "cells": [location],
                }

                entries.append(entry)
                previous = entry

                if len(entries) > 3000:
                    raise ValueError(
                        "Слишком много целей. Разделите выгрузку."
                    )

    if not recognized or not entries:
        raise ValueError(
            "Не найдена таблица с заголовком "
            "«Оқу мақсаттары / Оқыту мақсаттары / Цели обучения» "
            "и стандартными кодами целей."
        )

    unique: dict[tuple[str, str], ParsedObjective] = {}

    for entry in entries:
        key = (entry["code"], entry["title"])

        if key in unique:
            target = unique[key]
            target["quarters"] = sorted(
                set(target["quarters"] + entry["quarters"])
            )
            target["cells"].extend(entry["cells"])

            if target["language_skill"] != entry["language_skill"]:
                target["language_skill"] = ""
                warnings.append(
                    f'{entry["code"]}: различаются навыки; '
                    "выберите вручную."
                )
        else:
            unique[key] = entry

    codes: dict[str, int] = defaultdict(int)

    for code, _ in unique:
        codes[code] += 1

    warnings.extend(
        f"{code}: несколько формулировок; каждая сохраняется со своими четвертями."
        for code, count in codes.items()
        if count > 1
    )

    return list(unique.values()), list(dict.fromkeys(warnings))


def merge_table_languages(kz, ru):
    left = defaultdict(list)
    right = defaultdict(list)
    rows = []
    for e in kz:
        left[e["code"]].append(e)
    for e in ru:
        right[e["code"]].append(e)
    for code in sorted(
            set(left) | set(right), key=lambda c: tuple(map(int, c.split(".")))
    ):
        a, b = left[code], right[code]
        pairs = (
            [(a[0], b[0])]
            if len(a) == len(b) == 1 and a[0]["quarters"] == b[0]["quarters"]
            else [(e, None) for e in a] + [(None, e) for e in b]
        )
        for k, r in pairs:
            e = k or r
            row = {
                key: e[key]
                for key in (
                    "code",
                    "grade_level",
                    "section_code",
                    "subsection_code",
                    "language_skill",
                )
            }
            row["quarters"] = sorted(
                set((k["quarters"] if k else []) + (r["quarters"] if r else []))
            )
            row["quarter"] = row["quarters"][0]
            for language, item in (("kz", k), ("ru", r)):
                row["title_" + language] = item["title"] if item else ""
                row["section_title_" + language] = item["section_title"] if item else ""
                row["subsection_title_" + language] = (
                    item["subsection_title"] if item else ""
                )
                row["source_cells_" + language] = item["cells"] if item else []
                row["source_pages_" + language] = []
                row["formula_suspected_" + language] = bool(item and (
                        any("=" in loc["raw"] for loc in item["cells"])
                        or len(item["cells"]) > 1
                        or item["title"].rstrip().endswith((":", "-", ","))
                        or len(item["title"].strip(" -–—")) < 5
                ))
            if k and r and k["quarters"] != r["quarters"]:
                row["quarter_conflict"] = True
            rows.append(row)
    for index, row in enumerate(rows):
        row["import_row_id"] = str(index)
    return rows
