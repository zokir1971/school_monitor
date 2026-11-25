"""Five-sheet regional workbook. Presentation only; no SQL or score calculation."""
from io import BytesIO

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, NamedStyle, PatternFill
from openpyxl.utils import get_column_letter

from app.core.ui_locale_context import ui_locale


def build(dto):
    kk = ui_locale.get() == 'kk'
    def label(ru, kz):return kz if kk else ru
    book = Workbook(write_only=True)
    for name, heading, number_format in [
        ('regional_body', False, 'General'), ('regional_number', False, '0.00'),
        ('regional_percent', False, '0.00%'), ('regional_heading', True, 'General'),
    ]:
        style = NamedStyle(name=name, font=Font(name='Calibri', size=11, bold=heading,
            color='FFFFFF' if heading else '101828'),
            alignment=Alignment(vertical='center', wrap_text=True), number_format=number_format)
        if heading:style.fill=PatternFill('solid',fgColor='344054')
        book.add_named_style(style)
    sheets = [
        (label('Регион свод', 'Өңір жиынтығы'), 'summary', dto.work_summaries),
        (label('Районы', 'Аудандар'), 'district', dto.rows),
        (label('Школы', 'Мектептер'), 'school', dto.school_rows),
        (label('Областные школы свод', 'Облыстық мектептер жиынтығы'), 'summary', dto.regional_work_summaries),
        (label('Областные школы', 'Облыстық мектептер'), 'school', dto.regional_rows),
    ]
    metrics = [
        ('total_students', label('Всего', 'Барлығы')),
        ('participated_students', label('Участвовали', 'Қатысқан')),
        ('absent_students', label('Не участвовали', 'Қатыспады')),
        ('excused_students', label('Освобождены', 'Босатылған')),
        ('not_completed_students', label('Не завершили', 'Аяқтамады')),
        ('grade_5_count', '5'), ('grade_4_count', '4'), ('grade_3_count', '3'), ('grade_2_count', '2'),
        ('average_score', label('Средний балл', 'Орташа балл')),
        ('average_percent', label('Средний %', 'Орташа %')),
        ('achievement_percent', label('Успеваемость %', 'Үлгерім %')),
        ('quality_percent', label('Качество %', 'Білім сапасы %')),
    ]
    percentages = {'average_percent', 'achievement_percent', 'quality_percent'}
    for title, kind, rows in sheets:
        sheet = book.create_sheet(title)
        keys = [('work_title', label('Оценочная работа', 'Бағалау жұмысы'))]
        if kind == 'summary':keys.append(('schools', label('Школ', 'Мектеп саны')))
        elif kind == 'district':keys += [('entity_id', label('ID района', 'Аудан ID')), ('entity_name', label('Район', 'Аудан'))]
        else:keys += [('entity_id', label('ID школы', 'Мектеп ID')), ('district_name', label('Район расположения', 'Орналасқан ауданы')), ('entity_name', label('Школа', 'Мектеп'))]
        columns = keys + metrics
        sheet.sheet_view.showGridLines = False
        sheet.sheet_format.defaultRowHeight = 30
        sheet.freeze_panes = 'C9' if kind == 'summary' else 'D9' if kind == 'district' else 'E9'
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.print_title_rows = '1:8'
        for index, (key, _) in enumerate(columns, 1):
            sheet.column_dimensions[get_column_letter(index)].width = 42 if key == 'work_title' else 35 if key == 'entity_name' else 25 if key == 'district_name' else 15

        def append(values, heading=False):
            cells = []
            for index, value in enumerate(values):
                if isinstance(value, str):value=ILLEGAL_CHARACTERS_RE.sub('',value)
                cell=WriteOnlyCell(sheet,value=value)
                if isinstance(value,str):cell.data_type='s'  # names/titles are never formulas
                key=columns[index][0] if index<len(columns) else ''
                cell.style='regional_heading' if heading else 'regional_percent' if key in percentages else 'regional_number' if key=='average_score' else 'regional_body'
                cells.append(cell)
            sheet.append(cells)

        last_column = get_column_letter(len(columns))
        sheet.merged_cells.add(f'A1:{last_column}1')
        for index in range(2, 7):
            sheet.merged_cells.add(f'B{index}:{last_column}{index}')
            sheet.row_dimensions[index].height = 26
        sheet.merged_cells.add(f'A7:{last_column}7')
        sheet.row_dimensions[1].height = 30
        sheet.row_dimensions[7].height = 34
        sheet.row_dimensions[8].height = 42
        append([title], True)
        append([label('Регион', 'Өңір'), dto.organization_name])
        append([label('Учебный год', 'Оқу жылы'), dto.academic_year_label])
        append([label('Предмет / параллель', 'Пән / параллель'),
            (dto.subject_name or label('Все предметы','Барлық пәндер'))+' / '+str(dto.grade_level or label('Все','Барлығы'))])
        append([label('Подчинение (фильтр)', 'Бағыныстылық (сүзгі)'),
            {'district':label('Районное','Аудандық'),'region':label('Областное','Облыстық')}.get(dto.governance,label('Все','Барлығы'))])
        append([label('Выбранная работа', 'Таңдалған жұмыс'), dto.work_title or label('Все работы','Барлық жұмыстар')])
        append([label('Каждая работа отдельно; разные работы не суммируются.', 'Әр жұмыс бөлек; әртүрлі жұмыстар қосылмайды.') +
                ('' if rows else ' '+label('По выбранным фильтрам нет результатов.','Таңдалған сүзгілер бойынша нәтижелер жоқ.'))])
        append([name for _, name in columns], True)
        for row in rows:
            values = []
            for key, _ in columns:
                if key == 'work_title':value = row.full_work_title or row.work_title
                elif key == 'schools':value = int(row.entity_name)
                else:value = getattr(row, key)
                if key in percentages:value = float(value / 100) if value is not None else None
                elif key == 'average_score':value = float(value) if value is not None else None
                values.append(value)
            append(values)
        sheet.auto_filter.ref=f'A8:{get_column_letter(len(columns))}{max(8,len(rows)+8)}'
    stream=BytesIO()
    book.save(stream)
    return stream.getvalue()
