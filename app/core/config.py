from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    # App settings
    app_name: str = "Digital Process Engineer"
    app_version: str = "1.0.0"
    debug: bool = False

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000

    # Timezone settings
    time_zone: str = "Europe/Moscow"

    # Database
    database_url: str = "postgresql://draw_chat:draw_chat_dev@localhost:5432/draw_chat"

    # Authentication
    secret_key: str = "dev-secret-change-me"
    token_ttl_days: int = 7

    # AI / LLM
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    ai_model: str = "anthropic/claude-3.5-sonnet"
    ai_verify_ssl: bool = True

    # Bootstrap admin
    bootstrap_admin_login: str = "admin"
    bootstrap_admin_password: str = "admin"

    # File upload
    max_upload_bytes: int = 20 * 1024 * 1024  # 20 MB

    # Sentry
    sentry_dsn: str = ""

    # LLM
    llm_payload_retention_days: int = 0
    llm_history_max_chars: int = 200_000

    # DXF Converter
    dxf_converter_url: str = "http://dxf-converter:8001"
    dxf_converter_timeout: float = 8.0

    # OpenTelemetry
    otel_service_name: str = "fastapi-template"
    otel_exporter_otlp_endpoint: str = "http://localhost:4318"
    otel_exporter_otlp_protocol: str = "http/protobuf"
    otel_traces_exporter: str = "otlp"
    otel_traces_sampler: str = "always_on"
    otel_metrics_exporter: str = "none"
    otel_logs_exporter: str = "none"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
