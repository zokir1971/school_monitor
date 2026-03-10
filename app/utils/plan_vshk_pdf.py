# app/utils/pdf/plan_vshk_pdf.py

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame
from reportlab.platypus import Flowable
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.platypus.tableofcontents import TableOfContents

from app.utils.font import register_cyrillic_fonts


@dataclass
class ApprovalMeta:
    district_name: str | None = None  # ✅ название района
    director_fio: str | None = None
    director_position: str | None = "Директор школы"
    approve_title: str | None = "УТВЕРЖДАЮ"
    school_name: str | None = None
    city: str | None = None


class PlanVshkPdf:
    FONT = "DejaVuSans"
    FONT_BOLD = "DejaVuSans-Bold"

    @staticmethod
    def _title_page(dto, meta: ApprovalMeta, font: str):
        styles = getSampleStyleSheet()

        p10 = ParagraphStyle("P10", parent=styles["BodyText"], fontName=PlanVshkPdf.FONT, fontSize=10, leading=12)
        p10l = ParagraphStyle("P10L", parent=p10, alignment=TA_LEFT)
        p10r = ParagraphStyle("P10R", parent=p10, alignment=TA_RIGHT)
        p10c = ParagraphStyle("P10C", parent=p10, alignment=TA_CENTER, fontName=PlanVshkPdf.FONT_BOLD)

        title_bold = ParagraphStyle(
            "tTITLE_BOLD",
            parent=styles["Heading1"],
            fontName=PlanVshkPdf.FONT_BOLD,
            fontSize=16,
            leading=20,
            alignment=TA_CENTER,
            spaceBefore=8,
            spaceAfter=8,
        )

        district = (meta.district_name or "__________")  # ✅ НАЗВАНИЕ района/города
        school = (meta.school_name or "__________________")  # ✅ НАЗВАНИЕ школы
        year = getattr(dto.plan, "academic_year", "") or ""
        fio = meta.director_fio or "________________________"

        # Верх: две колонки
        left_block = [
            Paragraph("<b>Келісемін:</b>", p10l),
            Paragraph(f"{district} қаласының білім", p10l),
            Paragraph("бөлімінің басшысы", p10l),
            Spacer(1, 6),
            Paragraph("___________Б.Төлімбет", p10l),
            Paragraph("«____»________20_____ж.", p10l),
        ]

        right_block = [
            Paragraph("<b>Бекітемін:</b>", p10r),
            Paragraph(f"{district}  білім бөлімі", p10r),
            Paragraph(f"«{school}» жалпы білім", p10r),
            Paragraph("беретін мектеп» КММ", p10r),
            Paragraph("директоры", p10r),
            Paragraph(fio, p10r),
            Paragraph("«_____»__________20____ж.", p10r),
        ]

        # ширина под A4 landscape (297mm) минус поля 12+12 = 273мм
        t = Table([[left_block, right_block]], colWidths=[136.5 * mm, 136.5 * mm])
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))

        center: list[Flowable] = [
            Spacer(1, 100),
            Paragraph(
                f"{district}  білім бөлімі «{school}»<br/>коммуналдық мемлекеттік мекемесінің  {year} оқу жылының",
                p10c),
            Spacer(1, 10),
            Paragraph("МЕКТЕПІШІЛІК БАҚЫЛАУ ЖОСПАРЫ", title_bold),
            Spacer(1, 200),
            Paragraph(f"{district}   {year} оқу жылы.", p10c),
        ]
        out: list[Flowable] = [t]
        out.extend(center)
        return out

    @staticmethod
    def _scale_col_widths(col_widths, target_width):
        total = sum(col_widths)
        if total <= 0:
            return col_widths
        k = target_width / total
        return [w * k for w in col_widths]

    @staticmethod
    def _fit_col_widths(col_widths, available_width):
        total = sum(col_widths)
        if total <= available_width:
            return col_widths
        k = available_width / total
        return [w * k for w in col_widths]

    @staticmethod
    def build(dto, *, meta: ApprovalMeta) -> bytes:
        buff = BytesIO()

        register_cyrillic_fonts()

        # Чтобы IDE не ругалась на doc.leftMargin/bottomMargin — держим margins в переменных
        left = 12 * mm
        right = 12 * mm
        top = 10 * mm
        bottom = 10 * mm

        page_w, page_h = landscape(A4)
        frame_w = page_w - left - right
        frame_h = page_h - top - bottom

        # BaseDocTemplate нужен для авто-содержания
        doc = BaseDocTemplate(
            buff,
            pagesize=landscape(A4),
            leftMargin=left,
            rightMargin=right,
            topMargin=top,
            bottomMargin=bottom,
            title="План ВШК",
        )

        frame = Frame(
            left,
            bottom,
            frame_w,
            frame_h,
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
            id="normal",
        )

        doc.addPageTemplates([
            PageTemplate(id="All", frames=[frame], onPage=PlanVshkPdf._footer(PlanVshkPdf.FONT))
        ])

        styles = getSampleStyleSheet()

        # Оставляем твой H для других мест (например титул/разделы если надо слева)
        h3 = ParagraphStyle(
            "H3",
            parent=styles["Heading3"],
            fontName=PlanVshkPdf.FONT,
            fontSize=12,
            leading=14,
            spaceAfter=6,
        )

        p = ParagraphStyle(
            "P",
            parent=styles["BodyText"],
            fontName=PlanVshkPdf.FONT,
            fontSize=9,
            leading=11,
        )

        small = ParagraphStyle(
            "SMALL",
            parent=p,
            fontSize=8,
            textColor=colors.grey,
        )

        # ✅ Заголовок 2-го и 3-го листа: по центру и "чуть ниже"
        h_center = ParagraphStyle(
            "HCENTER",
            parent=styles["Heading2"],
            fontName=PlanVshkPdf.FONT_BOLD,
            fontSize=13,
            leading=14,
            alignment=TA_CENTER,
            spaceBefore=4,
            spaceAfter=4,
        )

        p_explain = ParagraphStyle(
            "PEXPLAIN",
            parent=styles["BodyText"],
            fontName=PlanVshkPdf.FONT,
            fontSize=8.5,  # чтобы влезло
            leading=9.5,
            alignment=TA_JUSTIFY,
            firstLineIndent=12.5 * mm,  # 1.25 см
            spaceAfter=2,
        )

        # ✅ TOC (Содержание) — можно тоже немного опустить
        toc = TableOfContents()
        toc.levelStyles = [
            ParagraphStyle(
                "TOC1",
                parent=p,
                leftIndent=0,
                firstLineIndent=0,
                spaceBefore=2,
                spaceAfter=2,
            ),
        ]

        # ✅ Какие заголовки попадают в TOC
        def after_flowable(flowable):
            if isinstance(flowable, Paragraph):
                style_name = getattr(flowable.style, "name", "")
                text = flowable.getPlainText().strip()
                if style_name == "H3" and text:
                    doc.notify("TOCEntry", (0, text, doc.page))

        doc.afterFlowable = after_flowable

        story = list()

        # =========================================================
        # 1) ТИТУЛ (лист 1)
        # =========================================================
        story.extend(PlanVshkPdf._title_page(dto, meta, PlanVshkPdf.FONT))
        story.append(PageBreak())
        # =========================================================
        # 2) СОДЕРЖАНИЕ (лист 2)
        # =========================================================
        story.append(Paragraph("МАЗМҰНЫ:", h_center))
        story.append(Spacer(1, 8))
        story.append(toc)
        story.append(PageBreak())

        # =========================================================
        # 3) ПОЯСНИТЕЛЬНАЯ (лист 3)
        # =========================================================
        story.append(Paragraph("ТҮСІНІК ХАТ", h_center))

        paragraphs = [
            (
                "Білім беру саласындағы инновациялармен байланысты динамикалық өзгерістер "
                "мектеп әкімшілігінен білім беру процесін тиімді іске асыру үшін "
                "өзгерістерді жоспарлау мен басқаруда жаңа тәсілдерді талап етеді."
            ),
            (
                "Білім беру ұйымының заманауи басшысында басқару құзыреттілігі болуы тиіс, "
                "өзінде стратегиялық көшбасшылық дағдыларын дамыта отырып, бүкіл мектеп "
                "командасының тиімді жұмыс нәтижесін көрсете алуы керек. Білім беру "
                "процесін ұйымдастыруда білім беру ұйымы қызметінің барлық бағыттары "
                "бойынша мектепішілік бақылауды сапалы жоспарлау мен жүзеге асыру маңызды."
            ),
            (
                "Бақылауға және жақсартуға байланысты басқарушылық міндеттерді іске асыру "
                "үшін жыл сайын әрбір мектеп «Орта, техникалық және кәсіптік, орта "
                "білімнен кейінгі білім беру ұйымдарының педагогтері жүргізуге міндетті "
                "құжаттардың Тізбесін және олардың нысандарын бекіту туралы» ҚР БҒМ "
                "2020 жылғы 6 сәуірдегі №130 бұйрығына сәйкес мектепішілік бақылау "
                "жоспарын әзірлейді (бұдан ары – МІБ)."
            ),
            (
                "Мектепішілік бақылау жоспары 6 бағыттан тұрады:"
            ),
            (
                "1. Нормативтік құжаттардың орындалуын және талаптарға сәйкес мектеп "
                "құжаттамасының жүргізілуін бақылау;"
            ),
            (
                "2. Оқу процесінің сапасын бақылау;"
            ),
            (
                "3. Оқушылардың білімдегі олқылықтарының орнын толтыру бойынша және "
                "үлгерімі төмен оқушылармен жұмысты бақылау;"
            ),
            (
                "4. Оқу-зерттеу қызметі;"
            ),
            (
                "5. Мұғалімнің шеберлік деңгейі мен әдістемелік дайындығының жай-күйін "
                "бақылау;"
            ),
            (
                "6. Тәрбие процесінің сапасын, іс-шараларды өткізуді бақылау."
            ),
            (
                "Мектепішілік бақылауды жоспарлау алдында аналитикалық деректерге "
                "сүйене отырып, білім беру қызметтерінің сапасын арттыру мәселесін "
                "шешу үшін күшті және әлсіз жақтарын, мүмкіндіктері мен қауіптерді "
                "анықтау мақсатында SWOT талдауын жүргізген жөн."
            ),
            (
                "6 бағытқа назар аудара отырып, әр мектептің әкімшілігі оқу жылының "
                "соңында бақылау объектілерін анықтайды және нақты білім беру "
                "ұйымында оқу-тәрбие процесін жетілдіру идеясына бағытталған "
                "басқару шешімдерін болжайды."
            ),
            (
                "Мектепішілік бақылау жоспарын іске асыру бойынша әзірленген "
                "Нұсқаулық мектеп басшысы мен орынбасарларын қамтитын басқару "
                "тобына мектепішілік бақылауды іске асыруға жауапты барлық "
                "бағыттар бойынша тиімді басқару шешімдерін қабылдаудың "
                "пәрменді моделін құруға көмектеседі."
            ),
            (
                "Нұсқаулықта нақты мектептің жағдайына бейімделуге болатын "
                "келесі материалдар берілген:"
            ),
            (
                "1. Бақылаудың әрбір бағыты бойынша «Басқару шешімдерінің матрицасы»;"
            ),
            (
                "2. Мектепішілік бақылау Жоспарының үлгілері мен жалпыланған нұсқалары."
            ),
            (
                "Ұсынылатын материалдың әр нұсқасы тәжірибелік тұрғыдан құнды, "
                "өйткені оқу-тәрбие процесінің барлық көрсеткіштерінің жақсаруымен "
                "қатар, күшті жақтарын арттырып, қауіптерді азайту үшін МІБ "
                "жоспарын қолайлы, өзекті етуге мүмкіндік береді."
            ),
            (
                "«Басқару шешімдерінің матрицасы» – қауіптерге негізделген "
                "объектілерді анықтауға арналған ыңғайлы алгоритм, ол сонымен "
                "қатар анықталған мәселені түзету немесе жою үшін басқарушылық "
                "шешімнің нұсқасын ұсынады. Жүргізілген жұмыстың тиімділігі мен "
                "тартылған әкімшілік ресурстардың орындылығы басқарушылық "
                "шешімдерді таңдауға байланысты болады."
            ),
            (
                "МІБ жоспарының үлгілері мен жалпыланған нұсқалары бақылау "
                "жоспарының тақырыбын, мақсатын, түрін және басқа элементтерін "
                "анықтауда қиындықтары бар мектеп командалары үшін пайдалы болады."
            ),
            (
                "МІБ жоспарлау кезінде SMART критерийлеріне сәйкес келетін "
                "(нақты, өлшенетін, қолжетімді, шынайы, уақытпен шектелген) "
                "бақылау мақсатын қоюға ерекше назар аудару қажет."
            ),
            (
                "Әдістемелік бірлестік жетекшілерін, тәжірибелі педагогтарды, "
                "шығармашылық топтарды жұмысқа тарта отырып, мектеп командасының "
                "әрбір субъектісінің жауапкершілік дәрежесін дұрыс бөлу маңызды. "
                "Әр мұғалім мен сынып жетекшісі өз жұмысының әлсіз жақтарын "
                "дербес анықтап, жағдайды өз құзыреті шегінде түзететін "
                "өзін-өзі бақылау құралдарын әзірлеу басқарудың тиімді "
                "қадамы бола алады."
            ),
            (
                "Анықталған мәселелер мен қауіптер бойынша басқару шешімдерінің "
                "матрицасы. Бақылау объектілері мен қауіптер алдыңғы оқу "
                "жылының нәтижелеріне егжей-тегжейлі жасалған SWOT талдауы "
                "негізінде анықталады. Директордың орынбасары, ӘБ жетекшісі, "
                "осы бағытқа жауапты мұғалім алгоритм бойынша келесі "
                "компоненттерді таңдай отырып әрекет етеді: бақылау "
                "объектілері – мәселелер, қауіптер – басқарушылық шешім "
                "нұсқасын таңдау – бақылаудың циклы нақты мектептің "
                "жағдайына байланысты жүреді."
            ),
        ]

        for paragraph in paragraphs:
            story.append(Paragraph(paragraph, p_explain))
        # =========================================================
        # 4) ОСНОВНОЙ КОНТЕНТ — направления и таблицы
        # =========================================================
        available_width = frame_w  # == ширина полезной области страницы

        for idx, b in enumerate(dto.directions, start=1):
            # со 2-го направления — новая страница
            if idx > 1:
                story.append(PageBreak())

            story.append(Paragraph(f"{idx}. {b.direction.short_title}", h3))
            if b.direction.full_title:
                story.append(Paragraph(b.direction.full_title, small))
            story.append(Spacer(1, 4))

            if b.rows4:
                story.append(Paragraph("Бақылау нысандары", small))
                story.append(Spacer(1, 2))
                story.append(PlanVshkPdf._table_rows4(b.rows4, PlanVshkPdf.FONT, available_width))
                story.append(Spacer(1, 10))

            if b.rows11:
                story.append(PageBreak())
                story.append(Paragraph("Атқарылатын іс-шаралардың мазмұны", small))
                story.append(Spacer(1, 2))
                story.append(PlanVshkPdf._table_rows11(b.rows11, PlanVshkPdf.FONT, available_width))
                story.append(Spacer(1, 12))

        # ✅ multiBuild обязателен: TOC требует 2 прохода
        doc.multiBuild(story)
        return buff.getvalue()

    @staticmethod
    def _footer(font: str):
        def draw(canvas, doc):
            canvas.saveState()
            canvas.setFont(font, 8)
            canvas.setFillColor(colors.grey)
            canvas.drawRightString(doc.pagesize[0] - 10 * mm, 7 * mm, f"Стр. {canvas.getPageNumber()}")
            canvas.restoreState()

        return draw

    @staticmethod
    def _cell(text: str | None, font: str) -> Paragraph:
        safe = (text or "").replace("\n", "<br/>")
        st = ParagraphStyle("CELL", fontName=font, fontSize=8, leading=10)
        return Paragraph(safe, st)

    @staticmethod
    def _table_style(font: str) -> TableStyle:
        return TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ])

    @staticmethod
    def _scale_with_fixed_first(col_widths, target_width):
        """
        Первая колонка фиксированная.
        Остальные масштабируются пропорционально.
        """
        first = col_widths[0]
        others = col_widths[1:]

        remaining_width = target_width - first
        total_others = sum(others)

        if total_others <= 0:
            return col_widths

        k = remaining_width / total_others
        scaled_others = [w * k for w in others]

        return [first] + scaled_others

    @staticmethod
    def _table_rows4(rows, font: str, available_width: float) -> Table:
        data = [["№", "Бақылау нысаны", "Мәселелер, тәуекелдер", "Басшылық шешімі"]]
        for i, r in enumerate(rows, start=1):
            data.append([
                PlanVshkPdf._cell(str(i), font),
                PlanVshkPdf._cell(getattr(r, "control_object", None), font),
                PlanVshkPdf._cell(getattr(r, "risk_text", None), font),
                PlanVshkPdf._cell(getattr(r, "decision_text", None), font),
            ])

        base = [10 * mm, 90 * mm, 90 * mm, 90 * mm]
        col_widths = PlanVshkPdf._scale_with_fixed_first(base, available_width)

        t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(PlanVshkPdf._table_style(font))
        return t

    @staticmethod
    def _table_rows11(rows, font: str, available_width: float) -> Table:
        data = [[
            "№",
            "Тақырып", "Мақсаты", "Бақылау нысаны", "Бақылау түрі",
            "Әдістер", "Мерзімі", "Жауаптылар",
            "Қарау орны", "Басшылық шешімі", "Екінші бақылау"
        ]]

        for i, r in enumerate(rows, start=1):
            data.append([
                PlanVshkPdf._cell(str(i), font),  # ✅ нумерация
                PlanVshkPdf._cell(getattr(r, "topic", None), font),
                PlanVshkPdf._cell(getattr(r, "goal", None), font),
                PlanVshkPdf._cell(getattr(r, "control_object", None), font),
                PlanVshkPdf._cell(getattr(r, "control_type", None), font),
                PlanVshkPdf._cell(getattr(r, "methods", None), font),
                PlanVshkPdf._cell(getattr(r, "deadlines", None), font),
                PlanVshkPdf._cell(getattr(r, "responsibles", None), font),
                PlanVshkPdf._cell(getattr(r, "review_place", None), font),
                PlanVshkPdf._cell(getattr(r, "management_decision", None), font),
                PlanVshkPdf._cell(getattr(r, "second_control", None), font),
            ])

        # Первая колонка (№) фиксированная 10 мм
        base = [
            10 * mm,  # №
            48 * mm, 44 * mm, 40 * mm, 32 * mm,
            32 * mm, 24 * mm, 28 * mm,
            36 * mm, 40 * mm, 36 * mm
        ]

        col_widths = PlanVshkPdf._scale_with_fixed_first(base, available_width)

        t = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(PlanVshkPdf._table_style(font))
        return t
