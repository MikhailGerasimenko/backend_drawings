"""Промпты LLM по команде: версии, активная версия, восстановление."""
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import PromptVersion, User, utcnow
from app.schema_modules.prompts import (
    DEFAULT_BLANK_ALLOWANCE_PROMPT,
    DEFAULT_DXF_PASSPORT_PROMPT,
    DEFAULT_PASSPORT_PROMPT,
    DEFAULT_TECHNOLOGY_PROMPT,
    PROMPT_KINDS,
)

DEFAULT_BY_KIND = {
    "passport": DEFAULT_PASSPORT_PROMPT,
    "technology": DEFAULT_TECHNOLOGY_PROMPT,
    "blank_allowance": DEFAULT_BLANK_ALLOWANCE_PROMPT,
    "passport_dxf": DEFAULT_DXF_PASSPORT_PROMPT,
}


def _validate_kind(kind: str) -> str:
    k = (kind or "").strip().lower()
    if k not in PROMPT_KINDS:
        raise ValueError(f"Неизвестный тип промпта: {kind}")
    return k


def get_active_prompt(db: Session, team_id: UUID, kind: str) -> str:
    """Текст активного системного промпта команды."""
    k = _validate_kind(kind)
    row = db.scalar(
        select(PromptVersion)
        .where(
            PromptVersion.team_id == team_id,
            PromptVersion.kind == k,
            PromptVersion.is_active.is_(True),
        )
        .limit(1)
    )
    if row:
        return row.text
    return DEFAULT_BY_KIND[k]


def ensure_team_prompts(db: Session, team_id: UUID, created_by: UUID | None = None) -> None:
    """Создать v1 для новой команды, если промптов ещё нет."""
    for kind, text in DEFAULT_BY_KIND.items():
        exists = db.scalar(
            select(PromptVersion.id)
            .where(PromptVersion.team_id == team_id, PromptVersion.kind == kind)
            .limit(1)
        )
        if exists:
            continue
        db.add(
            PromptVersion(
                team_id=team_id,
                kind=kind,
                text=text,
                version_no=1,
                is_active=True,
                created_by=created_by,
                created_at=utcnow(),
            )
        )
    db.flush()


def list_versions(db: Session, team_id: UUID, kind: str) -> list[PromptVersion]:
    k = _validate_kind(kind)
    return list(
        db.scalars(
            select(PromptVersion)
            .where(PromptVersion.team_id == team_id, PromptVersion.kind == k)
            .order_by(PromptVersion.version_no.desc())
        ).all()
    )


def save_new_prompt(
    db: Session, team_id: UUID, kind: str, text: str, user_id: UUID | None
) -> PromptVersion:
    k = _validate_kind(kind)
    body = (text or "").strip()
    if not body:
        raise ValueError("Текст промпта не может быть пустым")

    max_v = db.scalar(
        select(func.max(PromptVersion.version_no)).where(
            PromptVersion.team_id == team_id,
            PromptVersion.kind == k,
        )
    ) or 0

    db.execute(
        update(PromptVersion)
        .where(PromptVersion.team_id == team_id, PromptVersion.kind == k)
        .values(is_active=False)
    )

    row = PromptVersion(
        team_id=team_id,
        kind=k,
        text=body,
        version_no=max_v + 1,
        is_active=True,
        created_by=user_id,
        created_at=utcnow(),
    )
    db.add(row)
    db.flush()
    return row


def restore_prompt_version(
    db: Session, team_id: UUID, version_id: UUID, user_id: UUID | None
) -> PromptVersion:
    target = db.get(PromptVersion, version_id)
    if not target or target.team_id != team_id:
        raise ValueError("Версия промпта не найдена")

    db.execute(
        update(PromptVersion)
        .where(PromptVersion.team_id == team_id, PromptVersion.kind == target.kind)
        .values(is_active=False)
    )
    target.is_active = True
    db.flush()
    return target


def creator_name(db: Session, user_id: UUID | None) -> str | None:
    if not user_id:
        return None
    u = db.get(User, user_id)
    return (u.display_name or u.login) if u else None
