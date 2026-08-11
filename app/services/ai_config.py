"""Конфиг подключения к моделям: env + app_config (только superuser в админке)."""
import os
from dataclasses import dataclass

<<<<<<< HEAD
from sqlalchemy import select
=======
>>>>>>> gitlab/dev
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AppConfig

# Температура по умолчанию (если в админке не задана)
DEFAULT_MODEL_TEMPERATURE = 0.2


@dataclass
class ModelConnection:
    base_url: str
    api_key: str
    model: str
    temperature: float = DEFAULT_MODEL_TEMPERATURE

    @property
    def use_mock(self) -> bool:
        if not (self.api_key or "").strip():
            return True
        # Тестовые модели из pytest/админки — без реального OpenRouter
        if (self.model or "").startswith("test/"):
            return True
        return False


def _parse_bool_cfg(val: str | None, default: bool) -> bool:
    if val is None or not str(val).strip():
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _parse_float_cfg(val: str | None, default: float) -> float:
    if val is None or not str(val).strip():
        return default
    try:
        return float(str(val).strip().replace(",", "."))
    except ValueError:
        return default


@dataclass
class AiConfig:
    passport: ModelConnection
    technology: ModelConnection
    blank_allowance: ModelConnection
    dxf_passport: ModelConnection
    verify_ssl: bool = True


def _cfg(db: Session, key: str, default: str = "") -> str:
    # pytest: mock без удаления ключей из dev-БД (см. tests/conftest.py)
    if os.environ.get("PYTEST_FORCE_AI_MOCK") == "1" and (
        key.endswith("ModelKey") or key == "openrouterApiKey"
    ):
        return ""
<<<<<<< HEAD
    row = db.scalars(select(AppConfig).where(AppConfig.key == key).limit(1)).first()
=======
    row = db.get(AppConfig, key)
>>>>>>> gitlab/dev
    return row.value if row and row.value is not None else default


def _conn(
    db: Session,
    base_key: str,
    key_key: str,
    model_key: str,
    temp_key: str,
    env_key: str,
    env_base: str,
    env_model: str,
) -> ModelConnection:
    # Обратная совместимость со старыми ключами
    legacy_key = _cfg(db, "openrouterApiKey") or env_key
    legacy_base = _cfg(db, "openrouterBaseUrl", env_base).rstrip("/")
    legacy_model = _cfg(db, "aiModel", env_model)

    api_key = _cfg(db, key_key) or legacy_key
    base_url = (_cfg(db, base_key) or legacy_base).rstrip("/")
    model = _cfg(db, model_key) or legacy_model
    temperature = _parse_float_cfg(_cfg(db, temp_key), DEFAULT_MODEL_TEMPERATURE)
    return ModelConnection(
        base_url=base_url, api_key=api_key, model=model, temperature=temperature
    )


def get_ai_verify_ssl(db: Session) -> bool:
    return _parse_bool_cfg(_cfg(db, "aiVerifySsl"), settings.ai_verify_ssl)


def get_ai_config(db: Session) -> AiConfig:
    passport_conn = _conn(
        db,
        "passportModelBaseUrl",
        "passportModelKey",
        "passportModelModel",
        "passportModelTemperature",
        settings.openrouter_api_key,
        settings.openrouter_base_url,
        settings.ai_model,
    )
    return AiConfig(
        verify_ssl=get_ai_verify_ssl(db),
        passport=passport_conn,
        technology=_conn(
            db,
            "technologyModelBaseUrl",
            "technologyModelKey",
            "technologyModelModel",
            "technologyModelTemperature",
            settings.openrouter_api_key,
            settings.openrouter_base_url,
            settings.ai_model,
        ),
        blank_allowance=_conn(
            db,
            "blankAllowanceModelBaseUrl",
            "blankAllowanceModelKey",
            "blankAllowanceModelModel",
            "blankAllowanceModelTemperature",
            settings.openrouter_api_key,
            settings.openrouter_base_url,
            settings.ai_model,
        ),
        dxf_passport=_conn(
            db,
            "dxfPassportModelBaseUrl",
            "dxfPassportModelKey",
            "dxfPassportModelModel",
            "dxfPassportModelTemperature",
            settings.openrouter_api_key,
            settings.openrouter_base_url,
            settings.ai_model,
        ),
    )
