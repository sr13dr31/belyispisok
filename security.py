import base64
import hashlib
import os
from functools import lru_cache
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken


def _get_secret_source() -> bytes:
    secret = os.getenv("PASSPORT_SECRET")
    if not secret:
        raise RuntimeError(
            "Не задан PASSPORT_SECRET — невозможно защитить паспортные данные."
        )
    return secret.encode("utf-8")


def _build_fernet(secret_source: bytes) -> Fernet:
    digest = hashlib.sha256(secret_source).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    return _build_fernet(_get_secret_source())


@lru_cache(maxsize=1)
def _get_legacy_fernet() -> Optional[Fernet]:
    legacy_secret = os.getenv("BOT_TOKEN")
    if not legacy_secret:
        return None
    return _build_fernet(legacy_secret.encode("utf-8"))


def encrypt_passport(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    token = _get_fernet().encrypt(value.strip().encode("utf-8"))
    return token.decode("utf-8")


def decrypt_passport(value: Optional[str]) -> Tuple[Optional[str], bool]:
    if not value:
        return None, False
    try:
        data = _get_fernet().decrypt(value.encode("utf-8"))
        return data.decode("utf-8"), False
    except InvalidToken:
        legacy_fernet = _get_legacy_fernet()
        if legacy_fernet:
            try:
                data = legacy_fernet.decrypt(value.encode("utf-8"))
                return data.decode("utf-8"), True
            except InvalidToken:
                pass
        # Если ранее данные хранились в открытом виде — просто вернуть исходное значение.
        return value, False
