"""Схемы сессий, замечаний, активного времени, фидбека."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SessionSummary(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime


class SessionFeedbackView(BaseModel):
    stars: int
    comment: str | None = None
    created_at: datetime
    editable: bool = False


class FieldRemark(BaseModel):
    """Точечное замечание к полю (FR-015)."""

    field: str = Field(min_length=1)
    label: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("Текст замечания обязателен")
        return t


class FieldDiff(BaseModel):
    """Изменение одного поля между предыдущей и текущей версией документа."""

    field: str
    label: str
    old: str | None = None
    new: str | None = None


class StageFieldRemarks(BaseModel):
    """Черновики замечаний по этапу (хранятся в sessions.field_remarks[stage])."""

    applied: list[FieldRemark] = Field(default_factory=list)
    general_draft: str | None = Field(default=None, max_length=2000)


class RemarksSubmitRequest(BaseModel):
    """Пакет отправки замечаний: точечные + общий текст (FR-011/FR-014)."""

    field_remarks: list[FieldRemark] = Field(default_factory=list)
    general_text: str | None = Field(default=None, max_length=2000)


class ActiveTimeRequest(BaseModel):
    """Прирост чистого активного времени пользователя в секундах (FR-008…FR-010)."""

    delta_seconds: int = Field(..., ge=0, le=86400)


class ActiveTimeResponse(BaseModel):
    user_active_seconds: int


class SessionDetail(BaseModel):
    id: UUID
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    passport: dict | None = None
    technology_text: str | None = None
    technology_json: dict | None = None
    selected_operations: list = Field(default_factory=list)
    blank_allowance: dict | None = None
    blank_allowance_approved: bool = False
    blank_allowance_step_enabled: bool = False
    drawing_preview_url: str | None = None
    drawing_mime: str | None = None
    drawing_sent_at: datetime | None = None
    events: list = Field(default_factory=list)
    show_feedback_prompt: bool = False
    feedback_submitted: bool = False
    session_feedback: SessionFeedbackView | None = None
    field_diffs: dict = Field(default_factory=dict)
    field_remarks: dict = Field(default_factory=dict)
    has_field_remarks: bool = False


class SessionFeedbackRequest(BaseModel):
    stars: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class TechnologyGenerateRequest(BaseModel):
    catalog_ids: list[UUID] = Field(min_length=1)


class DrawingUploadResponse(BaseModel):
    preview_url: str
    status: str


class CreateSessionRequest(BaseModel):
    title: str | None = None
