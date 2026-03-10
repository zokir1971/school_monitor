# app/utils/fonts.py

from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


def register_cyrillic_fonts():
    base_dir = Path(__file__).resolve().parent.parent
    fonts_dir = base_dir / "assets" / "fonts"

    regular = fonts_dir / "DejaVuSans.ttf"
    bold = fonts_dir / "DejaVuSans-Bold.ttf"

    # Регистрируем обычный
    pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))

    # Регистрируем жирный
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))

    # регистрируем семейство
    pdfmetrics.registerFontFamily(
        "DejaVuSans",
        normal="DejaVuSans",
        bold="DejaVuSans-Bold",
        italic="DejaVuSans",
        boldItalic="DejaVuSans-Bold",
    )