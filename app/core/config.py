"""Настройки из переменных окружения (.env / docker compose)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://draw_chat:draw_chat_dev@localhost:5432/draw_chat"
    secret_key: str = "dev-secret-change-me"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_model: str = "anthropic/claude-3.5-sonnet"
    # false — для LiteLLM/прокси с самоподписанным TLS (только dev/внутренняя сеть)
    ai_verify_ssl: bool = True
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: str = "admin"
    token_ttl_days: int = 7
    max_upload_bytes: int = 20 * 1024 * 1024
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    # 0 — бессрочное хранение payload в llm_requests_log (purge отключён)
    llm_payload_retention_days: int = 0
    # Бюджет истории переписки LLM в символах (~50k токенов по эвристике символы/4);
    # настраивается под лимит контекста модели — specs/002 research R-03 / FR-010
    llm_history_max_chars: int = 200_000
    dxf_converter_url: str = "http://dxf-converter:8001"
    dxf_converter_timeout: float = 8.0


settings = Settings()
"""Настройки из переменных окружения (.env / docker compose)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://draw_chat:draw_chat_dev@localhost:5432/draw_chat"
    secret_key: str = "dev-secret-change-me"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_model: str = "anthropic/claude-3.5-sonnet"
    # false — для LiteLLM/прокси с самоподписанным TLS (только dev/внутренняя сеть)
    ai_verify_ssl: bool = True
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: str = "admin"
    token_ttl_days: int = 7
    max_upload_bytes: int = 20 * 1024 * 1024
    sentry_dsn: str = ""
    sentry_environment: str = "development"
    # 0 — бессрочное хранение payload в llm_requests_log (purge отключён)
    llm_payload_retention_days: int = 0
    # Бюджет истории переписки LLM в символах (~50k токенов по эвристике символы/4);
    # настраивается под лимит контекста модели — specs/002 research R-03 / FR-010
    llm_history_max_chars: int = 200_000
    dxf_converter_url: str = "http://dxf-converter:8001"
    dxf_converter_timeout: float = 8.0


settings = Settings()
