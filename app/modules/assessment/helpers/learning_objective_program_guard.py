"""Fail-closed PDF programme scope checks; no database access."""

from __future__ import annotations
import io
import re
import pdfplumber
from app.modules.assessment.helpers.learning_objective_pdf_import import (
    pages_from_string,
)

# Exact bilingual subject names, never substring matching.
SUBJECT_PAIRS = (
    ("информатика", "информатика"),
    ("математика", "математика"),
    ("алгебра", "алгебра"),
    ("геометрия", "геометрия"),
    ("физика", "физика"),
    ("химия", "химия"),
    ("биология", "биология"),
    ("география", "география"),
    ("қазақ тілі", "казахский язык"),
    ("қазақ әдебиеті", "казахская литература"),
    ("қазақ тілі мен әдебиеті", "казахский язык и литература"),
    ("орыс тілі", "русский язык"),
    ("орыс әдебиеті", "русская литература"),
    ("орыс тілі мен әдебиеті", "русский язык и литература"),
    ("ағылшын тілі", "английский язык"),
    ("қазақстан тарихы", "история казахстана"),
    ("дүниежүзі тарихы", "всемирная история"),
    ("жаратылыстану", "естествознание"),
    ("дүниетану", "познание мира"),
)


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip(' "«»')


def subject_key(value: str) -> str:
    name = normalize(value)
    return next((kz for kz, ru in SUBJECT_PAIRS if name in (kz, ru)), name)


def page_program(text: str) -> dict | None:
    lines = text.splitlines()
    # A genuine programme heading must start a line, not occur in a prose reference.
    for index, line in enumerate(lines):
        chunk = " ".join(lines[index : index + 5])
        if re.match(r"Типовая учебная программа по учебному предмету", line, re.I):
            match = re.search(
                r"[\"«]([^\"»]+)[\"»].*?для\s+(\d+)\s*[-–]\s*(\d+)\s*классов",
                chunk,
                re.I,
            )
        elif (
            re.match(r"(?:[\"«]|.*?сыныптарына)", line)
            and "үлгілік оқу бағдарламасы" in chunk.lower()
        ):
            match = re.search(
                r"[\"«]([^\"»]+)[\"»].*?(\d+)\s*[-–]\s*(\d+)\s*[-–]?\s*сынып",
                chunk,
                re.I,
            )
            if match is None:
                match = re.search(
                    r"(\d+)\s*[-–]\s*(\d+)\s*[-–]?\s*сынып.*?[\"«]([^\"»]+)[\"»]",
                    chunk,
                    re.I,
                )
                if match:
                    return dict(
                        subject=subject_key(match[3]),
                        grade_from=int(match[1]),
                        grade_to=int(match[2]),
                        title=chunk,
                    )
        else:
            continue
        if match is None:
            raise ValueError(
                "Заголовок программы распознан неоднозначно. Импорт остановлен."
            )
        return dict(
            subject=subject_key(match[1]),
            grade_from=int(match[2]),
            grade_to=int(match[3]),
            title=chunk,
        )
    # An unsupported programme heading is a boundary, never permission to keep
    # attributing later pages to the previous programme.
    if re.search(r"типовая учебная программа|үлгілік оқу бағдарламасы", text, re.I):
        raise ValueError(
            "Обнаружен неподдерживаемый заголовок программы. Импорт остановлен; требуется проверка структуры PDF."
        )
    return None


def validate_binding(
    binding: object, *, subject_name: str, meta: dict, pages: list[int]
) -> None:
    if not isinstance(binding, dict) or binding.get("version") != 1:
        raise ValueError(
            "Предпросмотр создан без проверки предмета. Загрузите PDF повторно."
        )
    if binding.get("subject") != subject_key(subject_name):
        raise ValueError("Предмет программы в PDF не совпадает с выбранным предметом.")
    if (
        not binding["grade_from"]
        <= meta["grade_from"]
        <= meta["grade_to"]
        <= binding["grade_to"]
    ):
        raise ValueError("Выбранные классы не входят в программу PDF.")
    if pages != binding.get("pages"):
        raise ValueError("Изменён диапазон проверенной программы.")


def verify_pdf_scope(
    content: bytes, *, pages: str, subject_name: str, meta: dict
) -> dict:
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        selected = pages_from_string(pages, total=len(pdf.pages))
        current = None
        selected_program = None
        start = None
        for number in range(1, max(selected) + 1):
            text = pdf.pages[number - 1].extract_text() or ""
            heading = page_program(text)
            if heading:
                # Shared boundary pages can contain the end of a different programme.
                if number in selected:
                    raise ValueError(
                        f"Страница {number} содержит начало программы. Выберите страницы после её заголовка."
                    )
                current, start = heading, number
            if number not in selected:
                continue
            if current is None:
                raise ValueError(
                    f"До страницы {number} не найден однозначный заголовок программы. Импорт запрещён."
                )
            if selected_program is not None and selected_program["start"] != start:
                raise ValueError(
                    "Диапазон пересекает разные программы. Выберите страницы одной программы."
                )
            selected_program = {
                **current,
                "start": start,
                "version": 1,
                "pages": selected,
            }
        validate_binding(
            selected_program, subject_name=subject_name, meta=meta, pages=selected
        )
        return selected_program
