# app/modules/assessment/exports/knowledge_quality_excel.py

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from app.modules.assessment.schemas.knowledge_quality_export_schemas import (
    KnowledgeQualityExportDTO,
    KnowledgeQualityExportRowDTO,
)


class KnowledgeQualityExcelExporter:
    """
    Excel-экспорт аналитики качества знаний.

    Не работает с БД.
    Не выполняет SQL.
    Не пересчитывает аналитику.

    Источник данных:
        KnowledgeQualityExportDTO

    Поддерживаемые уровни:
        school
        district
        region

    Структура workbook:
        school/district: сводка и детализация;
        region (regional_layout): пять листов региона и двух видов подчинения.
    """

    SUMMARY_SHEET_NAME = "Жиынтық"

    # Excel хранит процент как 0.70,
    # а отображает как 70,00 %.
    PERCENT_NUMBER_FORMAT = "0.00 %"

    DECIMAL_NUMBER_FORMAT = "0.00"

    # =====================================================
    # COLORS
    # =====================================================

    COLOR_PRIMARY = "344054"
    COLOR_PRIMARY_DARK = "1D2939"

    COLOR_HEADER = "475467"

    COLOR_LIGHT = "F2F4F7"
    COLOR_LIGHTER = "F9FAFB"

    COLOR_BORDER = "D0D5DD"

    COLOR_TEXT = "101828"
    COLOR_TEXT_MUTED = "667085"

    COLOR_WHITE = "FFFFFF"

    # =====================================================
    # PUBLIC
    # =====================================================

    @classmethod
    def build(
        cls,
        dto: KnowledgeQualityExportDTO,
    ) -> bytes:
        """
        Сформировать XLSX и вернуть содержимое файла
        как bytes.

        Подходит для StreamingResponse / Response.
        """

        if dto.scope == 'region' and dto.regional_layout:
            from app.modules.assessment.exporters.regional_knowledge_quality_excel import build
            return build(dto)

        if dto.all_works:
            return cls._build_all_work_workbook(dto)

        workbook = Workbook()

        # Стандартный лист используем под summary.
        summary_sheet = workbook.active
        summary_sheet.title = (
            cls.SUMMARY_SHEET_NAME
        )

        cls._build_summary_sheet(
            summary_sheet,
            dto=dto,
        )

        detail_sheet = workbook.create_sheet(
            cls._detail_sheet_name(
                dto.scope
            )
        )

        cls._build_detail_sheet(
            detail_sheet,
            dto=dto,
        )

        if dto.work_title:
            for sheet in (summary_sheet, detail_sheet):
                width = max(sheet.max_column, 4)
                sheet.merge_cells(start_row=2, start_column=1, end_row=2, end_column=width)
                cell = sheet.cell(row=2, column=1, value=dto.work_title)
                cell.alignment = Alignment(vertical='center', wrap_text=True)
                cell.font = Font(bold=True, color=cls.COLOR_PRIMARY)
                sheet.row_dimensions[2].height = 44

        buffer = BytesIO()

        workbook.save(
            buffer
        )

        buffer.seek(0)

        return buffer.getvalue()

    @classmethod
    def _build_all_work_workbook(cls, dto):
        from app.core.ui_locale_context import ui_locale
        from openpyxl.comments import Comment
        from collections import defaultdict
        kk = ui_locale.get() == 'kk'
        def label(ru,kz):return kz if kk else ru
        workbook = Workbook()
        summary = workbook.active
        summary.title = label('Сводный','Жиынтық')
        detail = workbook.create_sheet(cls._detail_sheet_name(dto.scope))
        work_names = defaultdict(set)
        for row in dto.rows:work_names[row.work_title].add(row.work_key)
        for sheet,rows,is_summary in ((summary,dto.work_summaries,True),(detail,dto.rows,False)):
            sheet.sheet_view.showGridLines = False
            sheet.page_setup.orientation = 'landscape'
            sheet.page_setup.fitToWidth = 1
            sheet.page_setup.fitToHeight = 0
            sheet.sheet_properties.pageSetUpPr.fitToPage = True
            sheet.freeze_panes = 'C9'
            sheet.merge_cells('A1:O1')
            cell = sheet['A1'];cell.value = dto.work_title or label('Все работы','Барлық жұмыстар')
            cell.font = Font(size=15,bold=True,color=cls.COLOR_WHITE)
            cell.fill = PatternFill('solid',fgColor=cls.COLOR_PRIMARY)
            cell.alignment = Alignment(horizontal='center',vertical='center')
            sheet.row_dimensions[1].height = 30
            metadata = [(label('Школа','Мектеп') if dto.scope in ('teacher','school') else label('Организация','Ұйым'),dto.organization_name)]
            if dto.scope == 'teacher':metadata.append((label('Учитель','Мұғалім'),dto.teacher_name or '—'))
            metadata += [(label('Учебный год','Оқу жылы'),dto.academic_year_label),
                         (label('Предмет / параллель','Пән / параллель'),dto.subject_name_display+' / '+dto.grade_level_label)]
            for index,(name,value) in enumerate(metadata,2):
                sheet.cell(index,1,name);cls._style_info_label(sheet.cell(index,1))
                sheet.merge_cells(start_row=index,start_column=2,end_row=index,end_column=15)
                cell = sheet.cell(index,2,value);cell.alignment = Alignment(vertical='center',wrap_text=True)
                cls._apply_border(cell);sheet.row_dimensions[index].height = 26
            sheet.merge_cells('A7:O7')
            sheet['A7'] = label('Итоги по каждой работе; разные работы не суммируются.','Әр жұмыс бойынша қорытынды; әртүрлі жұмыстар қосылмайды.') if is_summary else label('Результаты по работам и объектам.','Жұмыстар мен нысандар бойынша нәтижелер.')
            entity = label('Классов','Сынып саны') if dto.scope in ('teacher','school') else label('Школ','Мектеп саны') if dto.scope == 'district' else label('Районов','Аудан саны')
            if not is_summary:entity = label('Класс','Сынып') if dto.scope in ('teacher','school') else label('Школа','Мектеп') if dto.scope == 'district' else label('Район','Аудан')
            headers = (label('Оценочная работа','Бағалау жұмысы'),entity,label('Всего','Барлығы'),label('Участвовали','Қатысқан'),
                label('Не участвовали','Қатыспады'),label('Освобождены','Босатылған'),label('Не завершили','Аяқтамады'),
                '5','4','3','2',label('Средний балл','Орташа балл'),label('Средний %','Орташа %'),label('Успеваемость %','Үлгерім %'),label('Качество %','Білім сапасы %'))
            for index,name in enumerate(headers,1):sheet.cell(8,index,name);cls._style_table_header(sheet.cell(8,index))
            sheet.row_dimensions[8].height = 36
            for index,row in enumerate(rows,9):
                name = row.work_title
                if len(work_names[name]) > 1:name += ' · '+row.work_key
                values = (name,row.entity_name,row.total_students,row.participated_students,row.absent_students,row.excused_students,row.not_completed_students,
                    row.grade_5_count,row.grade_4_count,row.grade_3_count,row.grade_2_count,cls._decimal_value(row.average_score),
                    cls._percent_value(row.average_percent),cls._percent_value(row.achievement_percent),cls._percent_value(row.quality_percent))
                for col,value in enumerate(values,1):
                    cell = sheet.cell(index,col,value);cls._apply_border(cell)
                    cell.alignment = Alignment(vertical='center',horizontal='left' if col in (1,2) else 'center',wrap_text=True)
                    if col >= 13:cell.number_format = cls.PERCENT_NUMBER_FORMAT
                    elif col == 12:cell.number_format = cls.DECIMAL_NUMBER_FORMAT
                sheet.cell(index,1).comment = Comment(row.full_work_title or row.work_title,'School Monitor')
            sheet.auto_filter.ref = 'A8:O'+str(max(8,len(rows)+8))
            sheet.print_title_rows = '1:8'
            for col in range(1,16):sheet.column_dimensions[get_column_letter(col)].width = 15 if col not in (1,2) else 25
            sheet.print_options.horizontalCentered = True
        buffer = BytesIO();workbook.save(buffer);return buffer.getvalue()

    # =====================================================
    # TEACHER ASSESSMENT GROUP RESULTS
    # =====================================================

    @classmethod
    def build_teacher_group_results(
            cls,
            *,
            page_data,
            objective_analytics=None,
    ) -> bytes:
        """
        Сформировать Excel для страницы:

            teacher/assessment/student_results.html

        Используются уже подготовленные page DTO.

        Workbook:

            1. Оқушылар нәтижелері

            2. Оқу мақсаттары
               только если Assessment содержит objectives.

        Метод:
            - не работает с БД;
            - не выполняет SQL;
            - не пересчитывает результаты;
            - не создаёт новую аналитику.
        """

        workbook = Workbook()

        # =================================================
        # STUDENTS
        # =================================================

        students_sheet = workbook.active
        students_sheet.title = (
            "Оқушылар нәтижелері"
        )

        cls._build_teacher_students_sheet(
            students_sheet,
            page_data=page_data,
        )

        # =================================================
        # OBJECTIVES
        # =================================================

        if (
                objective_analytics is not None
                and objective_analytics.objectives
        ):
            objectives_sheet = (
                workbook.create_sheet(
                    "Оқу мақсаттары"
                )
            )

            cls._build_teacher_objectives_sheet(
                objectives_sheet,
                page_data=page_data,
                objective_analytics=(
                    objective_analytics
                ),
            )

        # =================================================
        # SAVE
        # =================================================

        buffer = BytesIO()

        workbook.save(
            buffer
        )

        buffer.seek(0)

        return buffer.getvalue()

    # =====================================================
    # TEACHER — STUDENTS SHEET
    # =====================================================

    @classmethod
    def _build_teacher_students_sheet(
            cls,
            sheet: Worksheet,
            *,
            page_data,
    ) -> None:
        """
        Лист результатов учеников
        конкретной AssessmentGroup.
        """

        sheet.sheet_view.showGridLines = False

        sheet.freeze_panes = "A7"

        sheet.page_setup.orientation = (
            "landscape"
        )

        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0

        sheet.sheet_properties.pageSetUpPr.fitToPage = (
            True
        )

        # =================================================
        # TITLE
        # =================================================

        sheet.merge_cells(
            "A1:G1"
        )

        title_cell = sheet["A1"]

        title_cell.value = (
            page_data.title
        )

        title_cell.font = Font(
            bold=True,
            size=14,
            color=cls.COLOR_WHITE,
        )

        title_cell.fill = PatternFill(
            fill_type="solid",
            fgColor=cls.COLOR_PRIMARY,
        )

        title_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        sheet.row_dimensions[1].height = 30

        # =================================================
        # INFO
        # =================================================

        info_rows = (
            (
                "Сынып",
                page_data.class_name,
            ),
            (
                "Пән",
                page_data.subject_name,
            ),
            (
                "Максималды балл",
                cls._decimal_value(
                    page_data.max_score
                ),
            ),
            (
                "Оқушы саны",
                page_data.student_count,
            ),
        )

        for offset, (
                label,
                value,
        ) in enumerate(
            info_rows,
            start=3,
        ):
            label_cell = sheet.cell(
                row=offset,
                column=1,
                value=label,
            )

            value_cell = sheet.cell(
                row=offset,
                column=2,
                value=value,
            )

            cls._style_info_label(
                label_cell
            )

            cls._apply_border(
                value_cell
            )

            value_cell.alignment = Alignment(
                vertical="center",
                wrap_text=True,
            )

        sheet["B5"].number_format = (
            cls.DECIMAL_NUMBER_FORMAT
        )

        # =================================================
        # TABLE
        # =================================================

        headers = (
            "№",
            "Оқушы",
            "Қатысу",
            "Балл",
            "Макс. балл",
            "Нәтиже %",
            "Баға",
        )

        header_row = 7

        for column, value in enumerate(
                headers,
                start=1,
        ):
            cell = sheet.cell(
                row=header_row,
                column=column,
                value=value,
            )

            cls._style_table_header(
                cell
            )

        # =================================================
        # DATA
        # =================================================

        first_data_row = 8

        for index, student in enumerate(
                page_data.students,
                start=1,
        ):
            row = (
                    first_data_row
                    + index
                    - 1
            )

            values = (
                index,
                student.student_name,
                student.participation_status_display,
                cls._decimal_value(
                    student.score
                ),
                (
                    cls._decimal_value(
                        page_data.max_score
                    )
                    if student.score is not None
                    else None
                ),
                cls._percent_value(
                    student.percent
                ),
                student.grade_display,
            )

            for column, value in enumerate(
                    values,
                    start=1,
            ):
                cell = sheet.cell(
                    row=row,
                    column=column,
                    value=value,
                )

                cls._apply_border(
                    cell
                )

                cell.alignment = Alignment(
                    horizontal=(
                        "left"
                        if column == 2
                        else "center"
                    ),
                    vertical="center",
                    wrap_text=(
                            column == 2
                    ),
                )

            sheet.cell(
                row=row,
                column=4,
            ).number_format = (
                cls.DECIMAL_NUMBER_FORMAT
            )

            sheet.cell(
                row=row,
                column=5,
            ).number_format = (
                cls.DECIMAL_NUMBER_FORMAT
            )

            sheet.cell(
                row=row,
                column=6,
            ).number_format = (
                cls.PERCENT_NUMBER_FORMAT
            )

        if page_data.students:
            last_row = (
                    first_data_row
                    + len(page_data.students)
                    - 1
            )

            sheet.auto_filter.ref = (
                f"A7:G{last_row}"
            )

        # =================================================
        # WIDTHS
        # =================================================

        widths = {
            1: 7,
            2: 34,
            3: 18,
            4: 12,
            5: 14,
            6: 14,
            7: 10,
        }

        cls._set_custom_widths(
            sheet,
            widths,
        )

    # =====================================================
    # TEACHER — OBJECTIVES SHEET
    # =====================================================

    @classmethod
    def _build_teacher_objectives_sheet(
            cls,
            sheet: Worksheet,
            *,
            page_data,
            objective_analytics,
    ) -> None:
        """
        Лист учебных целей конкретной AssessmentGroup.

        Данные полностью соответствуют
        блоку "Оқу мақсаттары"
        в student_results.html.
        """

        sheet.sheet_view.showGridLines = False

        sheet.freeze_panes = "A7"

        sheet.page_setup.orientation = (
            "landscape"
        )

        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0

        sheet.sheet_properties.pageSetUpPr.fitToPage = (
            True
        )

        # =================================================
        # TITLE
        # =================================================

        sheet.merge_cells(
            "A1:H1"
        )

        title_cell = sheet["A1"]

        title_cell.value = (
            f"{page_data.title} — "
            "Оқу мақсаттары"
        )

        title_cell.font = Font(
            bold=True,
            size=14,
            color=cls.COLOR_WHITE,
        )

        title_cell.fill = PatternFill(
            fill_type="solid",
            fgColor=cls.COLOR_PRIMARY,
        )

        title_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        sheet.row_dimensions[1].height = 30

        # =================================================
        # INFO
        # =================================================

        info_rows = (
            (
                "Сынып",
                page_data.class_name,
            ),
            (
                "Пән",
                page_data.subject_name,
            ),
            (
                "Оқу мақсаттары",
                len(
                    objective_analytics.objectives
                ),
            ),
        )

        for offset, (
                label,
                value,
        ) in enumerate(
            info_rows,
            start=3,
        ):
            label_cell = sheet.cell(
                row=offset,
                column=1,
                value=label,
            )

            value_cell = sheet.cell(
                row=offset,
                column=2,
                value=value,
            )

            cls._style_info_label(
                label_cell
            )

            cls._apply_border(
                value_cell
            )

            value_cell.alignment = Alignment(
                vertical="center",
                wrap_text=True,
            )

        # =================================================
        # TABLE
        # =================================================

        headers = (
            "№",
            "Оқу мақсатының коды",
            "Оқу мақсаты",
            "Макс. балл",
            "Қатысқан",
            "Жиналған балл",
            "Мүмкін балл",
            "Меңгеру %",
        )

        header_row = 7

        for column, value in enumerate(
                headers,
                start=1,
        ):
            cell = sheet.cell(
                row=header_row,
                column=column,
                value=value,
            )

            cls._style_table_header(
                cell
            )

        # =================================================
        # DATA
        # =================================================

        first_data_row = 8

        for index, objective in enumerate(
                objective_analytics.objectives,
                start=1,
        ):
            row = (
                    first_data_row
                    + index
                    - 1
            )

            values = (
                index,

                objective.objective_code,

                objective.objective_title,

                cls._decimal_value(
                    objective.objective_max_score
                ),

                objective.participated_students,

                cls._decimal_value(
                    objective.score_sum
                ),

                cls._decimal_value(
                    objective.max_score_sum
                ),

                cls._percent_value(
                    objective.mastery_percent
                ),
            )

            for column, value in enumerate(
                    values,
                    start=1,
            ):
                cell = sheet.cell(
                    row=row,
                    column=column,
                    value=value,
                )

                cls._apply_border(
                    cell
                )

                cell.alignment = Alignment(
                    horizontal=(
                        "left"
                        if column in (
                            2,
                            3,
                        )
                        else "center"
                    ),
                    vertical="center",
                    wrap_text=column in (2, 3)
                )

            for column in (
                    4,
                    6,
                    7,
            ):
                sheet.cell(
                    row=row,
                    column=column,
                ).number_format = (
                    cls.DECIMAL_NUMBER_FORMAT
                )

            sheet.cell(
                row=row,
                column=8,
            ).number_format = (
                cls.PERCENT_NUMBER_FORMAT
            )

        if objective_analytics.objectives:
            last_row = (
                    first_data_row
                    + len(objective_analytics.objectives)
                    - 1
            )

            sheet.auto_filter.ref = (
                f"A7:H{last_row}"
            )

        # =================================================
        # WIDTHS
        # =================================================

        widths = {
            1: 7,
            2: 20,
            3: 52,
            4: 14,
            5: 12,
            6: 17,
            7: 15,
            8: 15,
        }

        cls._set_custom_widths(
            sheet,
            widths,
        )

    # =====================================================
    # SUMMARY SHEET
    # =====================================================

    @classmethod
    def _build_summary_sheet(
        cls,
        sheet: Worksheet,
        *,
        dto: KnowledgeQualityExportDTO,
    ) -> None:
        summary = dto.summary

        # -------------------------------------------------
        # Page settings
        # -------------------------------------------------

        sheet.sheet_view.showGridLines = False

        sheet.freeze_panes = "A3"

        sheet.page_setup.orientation = (
            "landscape"
        )

        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0

        sheet.sheet_properties.pageSetUpPr.fitToPage = (
            True
        )

        # =================================================
        # TITLE
        # =================================================

        sheet.merge_cells(
            "A1:D1"
        )

        title_cell = sheet["A1"]

        title_cell.value = dto.title

        title_cell.font = Font(
            bold=True,
            size=15,
            color=cls.COLOR_WHITE,
        )

        title_cell.fill = PatternFill(
            fill_type="solid",
            fgColor=cls.COLOR_PRIMARY,
        )

        title_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        sheet.row_dimensions[1].height = 30

        # =================================================
        # ORGANIZATION / FILTER INFO
        # =================================================

        if dto.scope == "teacher":
            info_rows = (
                (
                    "Мектеп",
                    dto.organization_name,
                ),
                (
                    "Мұғалім",
                    dto.teacher_name or "—",
                ),
                (
                    "Оқу жылы",
                    dto.academic_year_label,
                ),
                (
                    "Пән / параллель",
                    (
                        f"{dto.subject_name_display} / "
                        f"{dto.grade_level_label}"
                    ),
                ),
            )

        else:
            info_rows = (
                (
                    "Ұйым",
                    dto.organization_name,
                ),
                (
                    "Оқу жылы",
                    dto.academic_year_label,
                ),
                (
                    "Пән",
                    dto.subject_name_display,
                ),
                (
                    "Параллель",
                    dto.grade_level_label,
                ),
            )

        start_row = 3

        for offset, (
            label,
            value,
        ) in enumerate(
            info_rows
        ):
            row = (
                start_row
                + offset
            )

            label_cell = sheet.cell(
                row=row,
                column=1,
                value=label,
            )

            value_cell = sheet.cell(
                row=row,
                column=2,
                value=value,
            )

            cls._style_info_label(
                label_cell
            )

            value_cell.alignment = Alignment(
                vertical="center",
                wrap_text=True,
            )

            cls._apply_border(
                value_cell
            )

        # =================================================
        # KPI TITLE
        # =================================================

        sheet.merge_cells(
            "A8:D8"
        )

        section_cell = sheet["A8"]

        section_cell.value = (
            "Жалпы көрсеткіштер"
        )

        cls._style_section_title(
            section_cell
        )

        # =================================================
        # NO SUMMARY
        # =================================================

        if summary is None:
            sheet.merge_cells(
                "A9:D11"
            )

            empty_cell = sheet["A9"]

            empty_cell.value = (
                "Аналитикалық деректер жоқ."
            )

            empty_cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

            empty_cell.font = Font(
                color=cls.COLOR_TEXT_MUTED,
            )

            cls._set_summary_widths(
                sheet
            )

            return

        # =================================================
        # KPI VALUES
        # =================================================

        kpi_rows = (
            (
                "Барлық оқушы",
                summary.total_students,
                "Қатысқандар",
                summary.participated_students,
            ),
            (
                "Қатыспады",
                summary.absent_students,
                "Себепті",
                summary.excused_students,
            ),
            (
                "Аяқтамады",
                summary.not_completed_students,
                "Орташа балл",
                cls._decimal_value(
                    summary.average_score
                ),
            ),
            (
                "Орташа %",
                cls._percent_value(
                    summary.average_percent
                ),
                "Үлгерім",
                cls._percent_value(
                    summary.achievement_percent
                ),
            ),
            (
                "Білім сапасы",
                cls._percent_value(
                    summary.quality_percent
                ),
                "",
                None,
            ),
        )

        for offset, values in enumerate(
            kpi_rows
        ):
            row = 9 + offset

            for column, value in enumerate(
                values,
                start=1,
            ):
                cell = sheet.cell(
                    row=row,
                    column=column,
                    value=value,
                )

                cls._apply_border(
                    cell
                )

                cell.alignment = Alignment(
                    vertical="center",
                    wrap_text=True,
                )

                # A и C — названия показателей.
                if column in (
                    1,
                    3,
                ):
                    cell.fill = PatternFill(
                        fill_type="solid",
                        fgColor=cls.COLOR_LIGHTER,
                    )

                    cell.font = Font(
                        bold=True,
                        color=cls.COLOR_TEXT,
                    )

        # Средний балл.
        sheet["D11"].number_format = (
            cls.DECIMAL_NUMBER_FORMAT
        )

        # Настоящие числовые проценты.
        sheet["B12"].number_format = (
            cls.PERCENT_NUMBER_FORMAT
        )

        sheet["D12"].number_format = (
            cls.PERCENT_NUMBER_FORMAT
        )

        sheet["B13"].number_format = (
            cls.PERCENT_NUMBER_FORMAT
        )

        # =================================================
        # GRADE DISTRIBUTION
        # =================================================

        sheet.merge_cells(
            "A15:D15"
        )

        grade_title = sheet["A15"]

        grade_title.value = (
            "Бағалар үлестірімі"
        )

        cls._style_section_title(
            grade_title
        )

        grade_headers = (
            "«5» алғандар",
            "«4» алғандар",
            "«3» алғандар",
            "«2» алғандар",
        )

        for column, value in enumerate(
            grade_headers,
            start=1,
        ):
            cell = sheet.cell(
                row=16,
                column=column,
                value=value,
            )

            cls._style_table_header(
                cell
            )

        grade_values = (
            summary.grade_5_count,
            summary.grade_4_count,
            summary.grade_3_count,
            summary.grade_2_count,
        )

        for column, value in enumerate(
            grade_values,
            start=1,
        ):
            cell = sheet.cell(
                row=17,
                column=column,
                value=value,
            )

            cell.font = Font(
                bold=True,
                size=12,
                color=cls.COLOR_TEXT,
            )

            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
            )

            cls._apply_border(
                cell
            )

        cls._set_summary_widths(
            sheet
        )

    # =====================================================
    # DETAIL SHEET
    # =====================================================

    @classmethod
    def _build_detail_sheet(
        cls,
        sheet: Worksheet,
        *,
        dto: KnowledgeQualityExportDTO,
    ) -> None:
        sheet.sheet_view.showGridLines = False

        sheet.freeze_panes = "A6"

        sheet.auto_filter.ref = None

        sheet.page_setup.orientation = (
            "landscape"
        )

        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0

        sheet.sheet_properties.pageSetUpPr.fitToPage = (
            True
        )

        # =================================================
        # TITLE
        # =================================================

        last_column = (
            "O"
            if dto.scope == "school"
            else "N"
        )

        sheet.merge_cells(
            f"A1:{last_column}1"
        )

        title_cell = sheet["A1"]

        title_cell.value = dto.title

        title_cell.font = Font(
            bold=True,
            size=14,
            color=cls.COLOR_WHITE,
        )

        title_cell.fill = PatternFill(
            fill_type="solid",
            fgColor=cls.COLOR_PRIMARY,
        )

        title_cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
        )

        sheet.row_dimensions[1].height = 30

        # =================================================
        # FILTER INFO
        # =================================================

        if dto.scope == "teacher":
            info = (
                "Мұғалім",
                dto.teacher_name or "—",
                "Оқу жылы",
                dto.academic_year_label,
                "Пән",
                dto.subject_name_display,
                "Параллель",
                dto.grade_level_label,
            )

        else:
            info = (
                "Ұйым",
                dto.organization_name,
                "Оқу жылы",
                dto.academic_year_label,
                "Пән",
                dto.subject_name_display,
                "Параллель",
                dto.grade_level_label,
            )

        for column, value in enumerate(
            info,
            start=1,
        ):
            cell = sheet.cell(
                row=3,
                column=column,
                value=value,
            )

            cell.alignment = Alignment(
                vertical="center",
                wrap_text=True,
            )

            cls._apply_border(
                cell
            )

            if column in (
                1,
                3,
                5,
                7,
            ):
                cell.fill = PatternFill(
                    fill_type="solid",
                    fgColor=cls.COLOR_LIGHT,
                )

                cell.font = Font(
                    bold=True,
                    color=cls.COLOR_TEXT,
                )

        # =================================================
        # TABLE HEADER
        # =================================================

        if dto.scope == "school":
            headers = (
                cls._entity_header(
                    dto.scope
                ),
                "Мұғалім",
                "Барлық оқушы",
                "Қатысқан",
                "Қатыспады",
                "Себепті",
                "Аяқтамады",
                "5",
                "4",
                "3",
                "2",
                "Орташа балл",
                "Орташа %",
                "Үлгерім %",
                "Білім сапасы %",
            )

        else:
            headers = (
                cls._entity_header(
                    dto.scope
                ),
                "Барлық оқушы",
                "Қатысқан",
                "Қатыспады",
                "Себепті",
                "Аяқтамады",
                "5",
                "4",
                "3",
                "2",
                "Орташа балл",
                "Орташа %",
                "Үлгерім %",
                "Білім сапасы %",
            )

        for column, value in enumerate(
            headers,
            start=1,
        ):
            cell = sheet.cell(
                row=5,
                column=column,
                value=value,
            )

            cls._style_table_header(
                cell
            )

        sheet.row_dimensions[5].height = 32

        # =================================================
        # DATA
        # =================================================

        first_data_row = 6

        if dto.rows:
            for index, item in enumerate(
                dto.rows
            ):
                row = (
                    first_data_row
                    + index
                )

                cls._write_detail_row(
                    sheet,
                    row=row,
                    item=item,
                    scope=dto.scope,
                )

            last_data_row = (
                first_data_row
                + len(dto.rows)
                - 1
            )

            # Excel filter.
            sheet.auto_filter.ref = (
                f"A5:{last_column}{last_data_row}"
            )

        else:
            sheet.merge_cells(
                f"A6:{last_column}8"
            )

            empty_cell = sheet["A6"]

            empty_cell.value = (
                "Таңдалған сүзгілер бойынша "
                "деректер табылмады."
            )

            empty_cell.font = Font(
                color=cls.COLOR_TEXT_MUTED,
            )

            empty_cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )

        cls._set_detail_widths(
            sheet,
            scope=dto.scope,
        )

    # =====================================================
    # DETAIL ROW
    # =====================================================

    @classmethod
    def _write_detail_row(
        cls,
        sheet: Worksheet,
        *,
        row: int,
        item: KnowledgeQualityExportRowDTO,
        scope: str,
    ) -> None:
        """
        Записать одну строку detail-таблицы.

        Для school scope дополнительно выводится
        колонка с учителями класса.
        """

        if scope == "school":
            values = (
                item.entity_name,
                item.teacher_names_display,

                item.total_students,
                item.participated_students,

                item.absent_students,
                item.excused_students,
                item.not_completed_students,

                item.grade_5_count,
                item.grade_4_count,
                item.grade_3_count,
                item.grade_2_count,

                cls._decimal_value(
                    item.average_score
                ),

                cls._percent_value(
                    item.average_percent
                ),

                cls._percent_value(
                    item.achievement_percent
                ),

                cls._percent_value(
                    item.quality_percent
                ),
            )

            decimal_column = 12

            percent_columns = (
                13,
                14,
                15,
            )

            left_aligned_columns = (
                1,
                2,
            )

        else:
            values = (
                item.entity_name,

                item.total_students,
                item.participated_students,

                item.absent_students,
                item.excused_students,
                item.not_completed_students,

                item.grade_5_count,
                item.grade_4_count,
                item.grade_3_count,
                item.grade_2_count,

                cls._decimal_value(
                    item.average_score
                ),

                cls._percent_value(
                    item.average_percent
                ),

                cls._percent_value(
                    item.achievement_percent
                ),

                cls._percent_value(
                    item.quality_percent
                ),
            )

            decimal_column = 11

            percent_columns = (
                12,
                13,
                14,
            )

            left_aligned_columns = (
                1,
            )

        for column, value in enumerate(
            values,
            start=1,
        ):
            cell = sheet.cell(
                row=row,
                column=column,
                value=value,
            )

            cls._apply_border(
                cell
            )

            cell.alignment = Alignment(
                horizontal=(
                    "left"
                    if column in left_aligned_columns
                    else "center"
                ),
                vertical="center",
                wrap_text=(
                    column in left_aligned_columns
                ),
            )

        sheet.cell(
            row=row,
            column=decimal_column,
        ).number_format = (
            cls.DECIMAL_NUMBER_FORMAT
        )

        for column in percent_columns:
            sheet.cell(
                row=row,
                column=column,
            ).number_format = (
                cls.PERCENT_NUMBER_FORMAT
            )

    # =====================================================
    # VALUE HELPERS
    # =====================================================

    @staticmethod
    def _decimal_value(
        value: Decimal | None,
    ) -> float | None:
        if value is None:
            return None

        return float(
            value
        )

    @staticmethod
    def _percent_value(
        value: Decimal | None,
    ) -> float | None:
        """
        В DTO:

            70.00

        В Excel должно храниться:

            0.70

        С number_format:

            0.00 %

        пользователь увидит:

            70,00 %

        При этом ячейка остаётся числом.
        """

        if value is None:
            return None

        return float(
            value
            / Decimal("100")
        )

    # =====================================================
    # LABELS
    # =====================================================

    @staticmethod
    def _detail_sheet_name(
            scope: str,
    ) -> str:
        if scope == "teacher":
            return "Сыныптар бойынша"

        if scope == "school":
            return "Сыныптар бойынша"

        if scope == "district":
            return "Мектептер бойынша"

        if scope == "region":
            return "Аудандар бойынша"

        return "Толық мәлімет"

    @staticmethod
    def _entity_header(
            scope: str,
    ) -> str:
        if scope == "teacher":
            return "Сынып"

        if scope == "school":
            return "Сынып"

        if scope == "district":
            return "Мектеп"

        if scope == "region":
            return "Аудан"

        return "Атауы"

    # =====================================================
    # STYLES
    # =====================================================

    @classmethod
    def _style_info_label(
        cls,
        cell,
    ) -> None:
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor=cls.COLOR_LIGHT,
        )

        cell.font = Font(
            bold=True,
            color=cls.COLOR_TEXT,
        )

        cell.alignment = Alignment(
            vertical="center",
        )

        cls._apply_border(
            cell
        )

    @classmethod
    def _style_section_title(
        cls,
        cell,
    ) -> None:
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor="E4E7EC",
        )

        cell.font = Font(
            bold=True,
            size=12,
            color=cls.COLOR_PRIMARY,
        )

        cell.alignment = Alignment(
            horizontal="left",
            vertical="center",
        )

    @classmethod
    def _style_table_header(
        cls,
        cell,
    ) -> None:
        cell.fill = PatternFill(
            fill_type="solid",
            fgColor=cls.COLOR_HEADER,
        )

        cell.font = Font(
            bold=True,
            color=cls.COLOR_WHITE,
        )

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center",
            wrap_text=True,
        )

        cls._apply_border(
            cell
        )

    @classmethod
    def _apply_border(
        cls,
        cell,
    ) -> None:
        side = Side(
            style="thin",
            color=cls.COLOR_BORDER,
        )

        cell.border = Border(
            left=side,
            right=side,
            top=side,
            bottom=side,
        )

    # =====================================================
    # COLUMN WIDTHS
    # =====================================================

    @staticmethod
    def _set_summary_widths(
        sheet: Worksheet,
    ) -> None:
        widths = {
            "A": 23,
            "B": 38,
            "C": 23,
            "D": 20,
        }

        for column, width in widths.items():
            sheet.column_dimensions[
                column
            ].width = width

    @staticmethod
    def _set_detail_widths(
        sheet: Worksheet,
        *,
        scope: str,
    ) -> None:
        if scope == "school":
            widths = {
                1: 26,
                2: 38,
                3: 14,
                4: 14,
                5: 14,
                6: 12,
                7: 14,
                8: 8,
                9: 8,
                10: 8,
                11: 8,
                12: 16,
                13: 15,
                14: 15,
                15: 18,
            }

        else:
            widths = {
                1: 38,
                2: 14,
                3: 14,
                4: 14,
                5: 12,
                6: 14,
                7: 8,
                8: 8,
                9: 8,
                10: 8,
                11: 16,
                12: 15,
                13: 15,
                14: 18,
            }

        for column, width in widths.items():
            letter = get_column_letter(
                column
            )

            sheet.column_dimensions[
                letter
            ].width = width

    @staticmethod
    def _set_custom_widths(
            sheet: Worksheet,
            widths: dict[int, float],
    ) -> None:
        for column, width in widths.items():
            sheet.column_dimensions[
                get_column_letter(
                    column
                )
            ].width = width
