import base64
import hashlib
import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


def _get_secret_source() -> bytes:
    secret = os.getenv("PASSPORT_SECRET") or os.getenv("BOT_TOKEN")
    if not secret:
        raise RuntimeError(
            "Не задан PASSPORT_SECRET или BOT_TOKEN — невозможно защитить паспортные данные."
        )
    return secret.encode("utf-8")


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    digest = hashlib.sha256(_get_secret_source()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_passport(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    token = _get_fernet().encrypt(value.strip().encode("utf-8"))
    return token.decode("utf-8")


def decrypt_passport(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        data = _get_fernet().decrypt(value.encode("utf-8"))
        return data.decode("utf-8")
    except InvalidToken:
        # Если ранее данные хранились в открытом виде — просто вернуть исходное значение.
        return value

