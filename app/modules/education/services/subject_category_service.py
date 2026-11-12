import re
from app.modules.education.repositories.subject_category_repo import SubjectCategoryRepo


class SubjectCategoryService:
    @staticmethod
    async def save(db, form, category_id=None):
        code = str(form.get('code', '')).strip()
        name_kz = str(form.get('name_kz', '')).strip()
        name_ru = str(form.get('name_ru', '')).strip()
        order = str(form.get('sort_order', '100')).strip()
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,79}', code):
            raise ValueError('Код категории: строчные латинские буквы, цифры, _ или -.')
        if not name_kz or not name_ru or len(name_kz) > 255 or len(name_ru) > 255:
            raise ValueError('Заполните названия KZ и RU, максимум 255 символов.')
        if not re.fullmatch(r'\d{1,6}', order) or int(order) > 100000:
            raise ValueError('Порядок категории: целое число от 0 до 100000.')
        categories = await SubjectCategoryRepo.list_all(db)
        current = next((c for c in categories if c['id'] == category_id), None)
        if category_id is not None and (current is None or current['code'] != code):
            raise ValueError('Категория не найдена или изменён её постоянный код.')
        if any(c['code'] == code and c['id'] != category_id for c in categories):
            raise ValueError('Категория с таким кодом уже существует.')
        return await SubjectCategoryRepo.save(db, dict(code=code, name_kz=name_kz, name_ru=name_ru,
                                                       sort_order=int(order)), category_id)
