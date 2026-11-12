"""Запустить один раз из корня school_monitor: python fix_template_imports.py."""
from pathlib import Path
import re

root = Path('app/web/templates')
if not root.is_dir():
    raise SystemExit('Запустите скрипт из корня school_monitor (где находится папка app).')
pattern = re.compile(
    r'({%\s*from\s+[\'\"][^\'\"]*(?:answer_key|question_content|_segments)\.html[\'\"]\s+import\s+[^%]*?)(\s*%})')
for path in sorted(root.rglob('*.html')):
    original = path.read_text(encoding='utf-8')


    def update(match):
        head = match.group(1).rstrip()
        if re.search(r'\bwith\s+context\s*$', head):
            return match.group(0)
        head = re.sub(r'\s+without\s+context\s*$', '', head)
        return head + ' with context' + match.group(2)


    changed = pattern.sub(update, original)
    if changed != original:
        path.write_text(changed, encoding='utf-8')
        print(f'Обновлён импорт: {path}')
print('Готово.')
