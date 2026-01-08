"""
Валидация входных данных
"""
import re
from typing import Optional, Tuple


def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация номера телефона.
    Возвращает (is_valid, error_message)
    """
    if not phone or not phone.strip():
        return False, "Номер телефона не может быть пустым."
    
    phone = phone.strip()
    # Убираем все нецифровые символы кроме +
    cleaned = re.sub(r'[^\d+]', '', phone)
    
    # Проверяем длину (минимум 10 цифр)
    digits = re.sub(r'[^\d]', '', cleaned)
    if len(digits) < 10:
        return False, "Номер телефона слишком короткий. Минимум 10 цифр."
    
    if len(digits) > 15:
        return False, "Номер телефона слишком длинный. Максимум 15 цифр."
    
    return True, None


def validate_passport(passport: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация паспортных данных (серия и номер).
    Возвращает (is_valid, error_message)
    """
    if not passport or not passport.strip():
        return False, "Паспортные данные не могут быть пустыми."
    
    passport = passport.strip()
    
    # Убираем пробелы и дефисы
    cleaned = re.sub(r'[\s-]', '', passport)
    
    # Проверяем, что только цифры
    if not cleaned.isdigit():
        return False, "Паспортные данные должны содержать только цифры (серия и номер)."
    
    # Проверяем длину (обычно 10 цифр: 4 серия + 6 номер)
    if len(cleaned) < 8:
        return False, "Паспортные данные слишком короткие. Ожидается серия (4 цифры) и номер (6 цифр)."
    
    if len(cleaned) > 12:
        return False, "Паспортные данные слишком длинные."
    
    return True, None


def validate_public_id(public_id: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация публичного ID (формат: M-123456 или C-123456).
    Возвращает (is_valid, error_message)
    """
    if not public_id or not public_id.strip():
        return False, "ID не может быть пустым."
    
    public_id = public_id.strip().upper()
    
    # Проверяем формат: буква-дефис-цифры
    pattern = r'^[MC]-\d{6}$'
    if not re.match(pattern, public_id):
        return False, "Неверный формат ID. Ожидается формат: M-123456 или C-123456"
    
    return True, None


def validate_full_name(full_name: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация ФИО.
    Возвращает (is_valid, error_message)
    """
    if not full_name or not full_name.strip():
        return False, "ФИО не может быть пустым."
    
    full_name = full_name.strip()
    
    # Проверяем длину
    if len(full_name) < 3:
        return False, "ФИО слишком короткое. Минимум 3 символа."
    
    if len(full_name) > 200:
        return False, "ФИО слишком длинное. Максимум 200 символов."
    
    # Проверяем, что есть хотя бы одна буква
    if not re.search(r'[а-яА-Яa-zA-Z]', full_name):
        return False, "ФИО должно содержать хотя бы одну букву."
    
    return True, None


def validate_company_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация названия компании.
    Возвращает (is_valid, error_message)
    """
    if not name or not name.strip():
        return False, "Название компании не может быть пустым."
    
    name = name.strip()
    
    if len(name) < 2:
        return False, "Название компании слишком короткое. Минимум 2 символа."
    
    if len(name) > 200:
        return False, "Название компании слишком длинное. Максимум 200 символов."
    
    return True, None


def validate_review_text(text: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация текста отзыва.
    Возвращает (is_valid, error_message)
    """
    if not text or not text.strip():
        return False, "Текст отзыва не может быть пустым."
    
    text = text.strip()
    
    if len(text) < 10:
        return False, "Текст отзыва слишком короткий. Минимум 10 символов."
    
    if len(text) > 5000:
        return False, "Текст отзыва слишком длинный. Максимум 5000 символов."
    
    return True, None


def validate_position(position: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация должности.
    Возвращает (is_valid, error_message)
    """
    if not position or not position.strip():
        return True, None  # Должность необязательна
    
    position = position.strip()
    
    if len(position) < 2:
        return False, "Название должности слишком короткое. Минимум 2 символа."
    
    if len(position) > 200:
        return False, "Название должности слишком длинное. Максимум 200 символов."
    
    return True, None


def validate_appeal_reason(reason: str) -> Tuple[bool, Optional[str]]:
    """
    Валидация причины жалобы.
    Возвращает (is_valid, error_message)
    """
    if not reason or not reason.strip():
        return False, "Причина жалобы не может быть пустой."
    
    reason = reason.strip()
    
    if len(reason) < 10:
        return False, "Причина жалобы слишком короткая. Минимум 10 символов."
    
    if len(reason) > 2000:
        return False, "Причина жалобы слишком длинная. Максимум 2000 символов."
    
    return True, None
