"""Trusted report definitions; form parameters cannot change the report type."""
REPORT_TYPES = {
    'knowledge_quality_table': dict(path='knowledge-quality', route='knowledge_quality',
                                    title_ru='Таблица качества знаний', title_kk='Білім сапасының кестесі'),
    'reading_speed_table': dict(path='reading-speed', route='reading_speed', title_ru='Таблица скорости чтения', title_kk='Оқу жылдамдығының кестесі', structured=True),
    'document_analysis': dict(path='document-analysis', route='document_analysis', title_ru='Анализ документов', title_kk='Құжаттарды талдау', structured=True),
    'teacher_analysis': dict(path='teacher-analysis', route='teacher_analysis', title_ru='Анализ работы учителя', title_kk='Мұғалім жұмысының талдауы'),
    'analytical_reference': dict(path='analytical-reference', route='analytical_reference', title_ru='Аналитическая справка', title_kk='Талдау анықтамасы', structured=True, final=True),
    'class_summary': dict(path='general-analysis', route='general_analysis',
                          title_ru='Таблица обобщённого анализа', title_kk='Жалпылама талдау кестесі'),
}
