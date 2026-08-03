"""SQLAlchemy-модели — specs/001-drawing-tech-assistant/data-model.md"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Опциональный шаг расчёта припусков после выбора операций (US2c)
    blank_allowance_step_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="team")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user")  # admin | user
    team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    team: Mapped[Team | None] = relationship(back_populates="users")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkSession(Base):
    """Рабочая сессия анализа чертежа (таблица sessions)."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), index=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft_upload", index=True)
    drawing_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Кто согласовал технологию (для окна оценки — specs/005)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    # Чертёж в БД (base64); Phase 3+ — отдельная таблица artifacts
    drawing_mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    drawing_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    drawing_preview_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    passport: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    technology_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    technology_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Выбранные операции перед генерацией технологии [{catalog_id, operation, equipment}, ...]
    selected_operations: Mapped[list] = mapped_column(JSONB, default=list)
    blank_allowance: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    blank_allowance_approved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blank_allowance_step_active: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    events: Mapped[list] = mapped_column(JSONB, default=list)
    # Память переписки LLM по этапам {passport|blank_allowance|technology: [turn,...]}
    # specs/002-llm-conversation-memory/data-model.md; без 50-cap (в отличие от events)
    llm_history: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Черновики замечаний к полям по этапам {stage: {applied:[...], general_draft}}
    # specs/006-field-remarks-diff/data-model.md; очищаются после успешной перегенерации
    field_remarks: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Метрики времени формирования технологии (specs/007); общее = agent + user
    # agent_seconds — серверное время агентских операций; user_active_seconds — чистое
    # активное время пользователя (фронтенд-таймер с паузой при простое 5 мин)
    agent_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    user_active_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Снимок доли неизменных полей по этапам на момент согласования (FR-018/FR-019)
    field_acceptance: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


# Мягкое удаление: сессия остаётся в БД, в UI скрыта (FR-027)
SESSION_STATUS_DELETED = "deleted"


class SessionFeedback(Base):
    """Оценка завершённой сессии — одна запись на session_id."""

    __tablename__ = "session_feedback"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_feedback_session_id"),
        CheckConstraint("stars >= 1 AND stars <= 5", name="ck_session_feedback_stars"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    stars: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class StatisticsAgg(Base):
    __tablename__ = "statistics_agg"

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), primary_key=True)
    sessions_total: Mapped[int] = mapped_column(Integer, default=0)
    remarks_passport_total: Mapped[int] = mapped_column(Integer, default=0)
    remarks_technology_total: Mapped[int] = mapped_column(Integer, default=0)
    total_duration_sec: Mapped[int] = mapped_column(BigInteger, default=0)


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)


class OperationCatalogEntry(Base):
    """Справочник пар «операция — оборудование» по команде."""

    __tablename__ = "operation_catalog"
    __table_args__ = (
        UniqueConstraint("team_id", "operation", "equipment", name="uq_operation_catalog"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), index=True)
    operation: Mapped[str] = mapped_column(String(255), nullable=False)
    equipment: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class PromptVersion(Base):
    """Версии системных промптов LLM по команде (passport | technology)."""

    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    __table_args__ = (UniqueConstraint("team_id", "user_id", name="uq_team_member"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(16), default="member")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserActionLog(Base):
    __tablename__ = "user_actions_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), index=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True, index=True
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)


class LlmRequestLog(Base):
    __tablename__ = "llm_requests_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    provider_response_cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
