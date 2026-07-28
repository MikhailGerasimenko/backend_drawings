"""Пароли и токены (совместимо с legacy pbkdf2)."""
import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from app.core.config import settings


def make_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000
    ).hex()


def verify_password(password: str, salt: str, password_hash: str) -> bool:
    return hash_password(password, salt) == password_hash


def new_token() -> str:
    return str(uuid.uuid4())


def generate_random_password(length: int = 12) -> str:
    """Случайный пароль для сброса администратором."""
    alphabet = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def token_expires_at() -> datetime:
    # Сессии входа без автоистечения; отзыв — сброс пароля / удаление auth_sessions суперпользователем
    return datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
