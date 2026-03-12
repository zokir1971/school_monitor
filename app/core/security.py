# app/core/security.py (Авторизация: хэш пароля, генерация кода, Детерминированный хэш для поиска)

from passlib.context import CryptContext

from passlib.exc import PasswordSizeError

import hashlib
import random
import string

from app.core.config import get_settings


pwd_context = CryptContext(schemes=["bcrypt_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return pwd_context.verify(password, password_hash)
    except (ValueError, PasswordSizeError):
        return False


def generate_registration_code() -> str:
    """
    Генерация короткого человеко-читаемого кода вида AA12 для администраторов L1, L2, L3.
    """
    letters = "".join(random.choices(string.ascii_uppercase, k=2))
    digits = "".join(random.choices(string.digits, k=2))
    return f"{letters}{digits}"


def registration_code_lookup_hash(code: str) -> str:
    """
    Детерминированный хэш для поиска:
    sha256(UPPER(code) + ':' + PEPPER)
    """
    settings = get_settings()
    pepper = settings.CODE_PEPPER

    normalized = code.strip().upper()
    raw = f"{normalized}:{pepper}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
