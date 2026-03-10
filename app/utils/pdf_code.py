from io import BytesIO
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from app.utils.font import register_cyrillic_fonts


def generate_codes_pdf(
    *,
    title: str,
    issued: list[dict],
    level_label: str | None = None,
    issuer_name: str | None = None,
    scope_label: str | None = None,
    scope_name: str | None = None,
    notes: str | None = None,
    context_header: str = "Контекст",
) -> bytes:
    register_cyrillic_fonts()

    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CyrTitle",
        parent=styles["Title"],
        fontName="DejaVuSans-Bold",
    )
    normal_style = ParagraphStyle(
        "CyrNormal",
        parent=styles["Normal"],
        fontName="DejaVuSans",
    )
    italic_style = ParagraphStyle(
        "CyrItalic",
        parent=styles["Italic"],
        fontName="DejaVuSans",
    )

    header_cell_style = ParagraphStyle(
        "CyrHeaderCell",
        parent=styles["Normal"],
        fontName="DejaVuSans-Bold",
        fontSize=10,
        leading=12,
        alignment=1,   # center
    )

    cell_style = ParagraphStyle(
        "CyrCell",
        parent=styles["Normal"],
        fontName="DejaVuSans",
        fontSize=9,
        leading=11,
        wordWrap="LTR",
        splitLongWords=True,
    )

    story = [
        Paragraph(f"<b>{title}</b>", title_style),
        Spacer(1, 8),
    ]

    if scope_label and scope_name:
        story.extend([
            Paragraph(f"{scope_label}: {scope_name}", normal_style),
            Spacer(1, 6),
        ])

    story.extend([
        Paragraph(
            "<br/>".join(
                [x for x in [
                    f"Дата формирования: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    f"Уровень: {level_label}" if level_label else None,
                    f"Выдал: {issuer_name}" if issuer_name else None,
                ] if x]
            ),
            normal_style,
        ),
        Spacer(1, 10),
    ])

    if notes:
        story.extend([
            Paragraph(notes, italic_style),
            Spacer(1, 10),
        ])

    def context(it: dict) -> str:
        return (
            it.get("region_name")
            or it.get("district_name")
            or it.get("school_name")
            or it.get("target_name")
            or "-"
        )

    table_data = [[
        Paragraph(context_header, header_cell_style),
        Paragraph("Код", header_cell_style),
        Paragraph("Квота", header_cell_style),
        Paragraph("Действует до", header_cell_style),
    ]]

    for item in issued:
        table_data.append([
            Paragraph(str(context(item)), cell_style),
            Paragraph(str(item.get("raw_code", "")), cell_style),
            Paragraph(str(item.get("quota_total", "")), cell_style),
            Paragraph(str(item.get("expires_at") or "без срока"), cell_style),
        ])

    table = Table(
        table_data,
        colWidths=[70 * mm, 45 * mm, 20 * mm, 35 * mm],
        repeatRows=1,
    )

    table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("ALIGN", (2, 1), (2, -1), "CENTER"),
            ("ALIGN", (3, 1), (3, -1), "CENTER"),
        ])
    )

    story.append(table)
    story.append(Spacer(1, 12))
    story.append(
        Paragraph(
            "Сохраните PDF и передайте коды адресатам. При утрате кодов может потребоваться повторная выдача.",
            normal_style,
        )
    )

    doc.build(story)

    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
