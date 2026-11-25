"""Numeric, filterable five-sheet dynamics export; no SQL or recalculation."""
from io import BytesIO
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment,Font,NamedStyle,PatternFill
from openpyxl.utils import get_column_letter

from app.core.ui_locale_context import ui_locale
from app.modules.assessment.enums import AssessmentCheckpoint as Checkpoint

CHECKPOINTS=(
    (Checkpoint.BASELINE,'Нулевой контроль','Нөлдік бақылау'),
    (Checkpoint.QUARTER_1,'I четверть','I тоқсан'),(Checkpoint.QUARTER_2,'II четверть','II тоқсан'),
    (Checkpoint.QUARTER_3,'III четверть','III тоқсан'),(Checkpoint.QUARTER_4,'IV четверть','IV тоқсан'),
    (Checkpoint.FINAL,'Годовой итог','Жылдық қорытынды'),
)


def build(dto):
    kk=ui_locale.get()=='kk'
    def label(ru,kz):return kz if kk else ru
    book=Workbook(write_only=True)
    for name,heading,number in [('dyn_body',False,'General'),('dyn_percent',False,'0.00%'),
                                 ('dyn_delta',False,'+0.00;-0.00;0.00'),('dyn_head',True,'General')]:
        style=NamedStyle(name=name,font=Font(name='Calibri',size=11,bold=heading,color='FFFFFF'if heading else'101828'),
                         alignment=Alignment(vertical='center',wrap_text=True),number_format=number)
        if heading:style.fill=PatternFill('solid',fgColor='344054')
        book.add_named_style(style)
    sheets=[
        (label('Регион свод','Өңір жиынтығы'),'summary',(dto.overall,)),
        (label('Районы','Аудандар'),'district',dto.districts),
        (label('Школы','Мектептер'),'school',dto.schools),
        (label('Областные школы свод','Облыстық мектептер жиынтығы'),'summary',(dto.regional,)),
        (label('Областные школы','Облыстық мектептер'),'school',dto.regional_schools),
    ]
    for title,kind,entities in sheets:
        sheet=book.create_sheet(title)
        columns=[]
        if kind!='summary':columns=[('id',label('ID школы','Мектеп ID')if kind=='school'else label('ID района','Аудан ID'))]
        if kind=='school':columns.append(('district_name',label('Район расположения','Орналасқан ауданы')))
        if kind!='summary':columns.append(('name',label('Школа','Мектеп')if kind=='school'else label('Район','Аудан')))
        columns += [('checkpoint',label('Контрольная точка','Бақылау нүктесі')),
                    ('total_students',label('Всего','Барлығы')),
                    ('participated_students',label('Участвовали','Қатысқан')),
                    ('quality_students',label('Оценки 4–5','4–5 бағалары')),
                    ('quality_percent',label('Качество %','Білім сапасы %')),
                    ('delta_previous_pp',label('Изменение к предыдущей, п.п.','Алдыңғы нүктеге өзгеріс, п.т.')),
                    ('delta_baseline_pp',label('Изменение к нулевому, п.п.','Нөлдік бақылауға өзгеріс, п.т.'))]
        last=get_column_letter(len(columns))
        sheet.sheet_view.showGridLines=False
        sheet.sheet_format.defaultRowHeight=30
        sheet.freeze_panes='B9'if kind=='summary'else'D9'if kind=='district'else'E9'
        sheet.page_setup.orientation='landscape';sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
        sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.print_title_rows='1:8'
        sheet.merged_cells.add(f'A1:{last}1');sheet.merged_cells.add(f'A7:{last}7')
        for index in range(2,7):sheet.merged_cells.add(f'B{index}:{last}{index}')
        for index,(key,_)in enumerate(columns,1):
            sheet.column_dimensions[get_column_letter(index)].width=36 if key=='name'else 27 if key in('checkpoint','district_name')else 23 if key.startswith('delta_')else 16
        sheet.row_dimensions[1].height=30;sheet.row_dimensions[7].height=36;sheet.row_dimensions[8].height=45

        def append(values,heading=False):
            cells=[]
            for index,value in enumerate(values):
                if isinstance(value,str):value=ILLEGAL_CHARACTERS_RE.sub('',value)
                cell=WriteOnlyCell(sheet,value=value)
                if isinstance(value,str):cell.data_type='s'
                key=columns[index][0]if index<len(columns)else''
                cell.style='dyn_head'if heading else'dyn_percent'if key=='quality_percent'else'dyn_delta'if key.startswith('delta_')else'dyn_body'
                cells.append(cell)
            sheet.append(cells)

        append([label('Динамика качества знаний — ','Білім сапасының динамикасы — ')+title],True)
        append([label('Регион','Өңір'),dto.region_name])
        append([label('Учебный год','Оқу жылы'),f'{dto.academic_year_start}/{dto.academic_year_start+1}'])
        append([label('Предмет','Пән'),dto.subject_name or label('Все предметы','Барлық пәндер')])
        append([label('Параллель','Сынып'),dto.grade_level if dto.grade_level is not None else label('Все','Барлығы')])
        append([label('Подчинение','Бағыныстылық'),{'district':label('Районное','Аудандық'),'region':label('Областное','Облыстық')}.get(dto.governance,label('Все','Барлығы'))])
        append([label('Изменение — в процентных пунктах; пустая ячейка означает отсутствие данных, не ноль.',
                      'Өзгеріс пайыздық тармақпен; бос ұяшық деректердің жоқтығын білдіреді, нөл емес.')])
        append([name for _,name in columns],True)
        count=0
        for entity in entities:
            by_checkpoint={point.checkpoint:point for point in entity.points}
            for checkpoint,ru,kz in CHECKPOINTS:
                point=by_checkpoint.get(checkpoint)
                values=[]
                for key,_ in columns:
                    if key in('id','name','district_name'):value=getattr(entity,key)
                    elif key=='checkpoint':value=kz if kk else ru
                    else:value=getattr(point,key)if point is not None else None
                    if key=='quality_percent':value=float(value/100)if value is not None else None
                    elif key.startswith('delta_'):value=float(value)if value is not None else None
                    values.append(value)
                append(values);count+=1
        sheet.auto_filter.ref=f'A8:{last}{max(8,count+8)}'
    stream=BytesIO();book.save(stream);return stream.getvalue()
