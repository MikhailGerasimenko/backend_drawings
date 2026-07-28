"""Pytest: DATABASE_URL из корневого .env (UTF-8) и понятная ошибка при недоступной БД."""
import os
from pathlib import Path

import pytest

# Корень репозитория (draw_chat_assist/), не backend/
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"

os.environ.setdefault("PGCLIENTENCODING", "UTF8")


def _apply_env_file() -> None:
    if not _ENV_FILE.is_file():
        return
    text = _ENV_FILE.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _db_ping_url(url: str) -> str | None:
    """None если подключение успешно, иначе текст ошибки."""
    try:
        from sqlalchemy import create_engine, text

        eng = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"client_encoding": "utf8"},
        )
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return None
    except Exception as exc:
        return str(exc)


_apply_env_file()
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://draw_chat:draw_chat_dev@127.0.0.1:5433/draw_chat",
)

# До импорта app.main: если 5432 занят локальным postgres — переключиться на Docker 5433
_init_url = os.environ.get("DATABASE_URL", "")
if _db_ping_url(_init_url) and ":5432/" in _init_url:
    _alt_url = _init_url.replace(":5432/", ":5433/", 1)
    if _db_ping_url(_alt_url) is None:
        os.environ["DATABASE_URL"] = _alt_url

# Pytest: mock AI без OpenRouter; ключи в app_config не трогаем (dev БД на :5433)
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["PYTEST_FORCE_AI_MOCK"] = "1"


def _db_ping() -> str | None:
    url = os.environ.get("DATABASE_URL", "")
    err = _db_ping_url(url)
    # На Windows часто занят 5432 локальным postgres — Docker слушает 5433
    if err and ":5432/" in url:
        alt = url.replace(":5432/", ":5433/", 1)
        if _db_ping_url(alt) is None:
            os.environ["DATABASE_URL"] = alt
            return None
    return err


@pytest.fixture(scope="session", autouse=True)
def _require_postgres():
    err = _db_ping()
    if err:
        pytest.fail(
            "PostgreSQL недоступен для pytest.\n"
            f"DATABASE_URL={os.environ.get('DATABASE_URL')}\n"
            f"Ошибка: {err}\n\n"
            "Частая причина на Windows: локальный PostgreSQL уже слушает 5432, "
            "а pytest подключается не к Docker.\n"
            "Решение: `docker compose up -d postgres` и в .env порт **5433** "
            "(см. docker-compose.yml и .env.example), либо остановите службу postgres Windows."
        )
