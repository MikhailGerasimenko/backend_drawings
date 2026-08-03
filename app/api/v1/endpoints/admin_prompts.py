"""Админка: системные промпты по команде (версии и восстановление)."""
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.deps import DbSession, StaffUser
from app.core.exceptions import AppError
from app.models import Team
from app.schema_modules.prompts import PROMPT_KINDS
from app.schemas.admin import BlankAllowanceStepRequest
from app.roles import ROLE_SUPERUSER, can_manage_team_prompts
from app.services.prompts import (
    DEFAULT_BY_KIND,
    creator_name,
    ensure_team_prompts,
    get_active_prompt,
    list_versions,
    restore_prompt_version,
    save_new_prompt,
)

router = APIRouter(prefix="/admin", tags=["admin-prompts"])


class PromptSaveRequest(BaseModel):
    team_id: UUID
    kind: str
    text: str = Field(min_length=1)


class PromptRestoreRequest(BaseModel):
    team_id: UUID
    version_id: UUID


class PromptDefaultRequest(BaseModel):
    team_id: UUID
    kind: str


def _resolve_team_id(actor: StaffUser, team_id: UUID | None) -> UUID:
    if actor.user_role == ROLE_SUPERUSER:
        if not team_id:
            raise AppError("VALIDATION_ERROR", "Укажите team_id", 400)
        return team_id
    if team_id and team_id != actor.team_id:
        raise AppError("FORBIDDEN", "Доступ только к промптам своей команды", 403)
    return actor.team_id


def _check_team(db: DbSession, team_id: UUID) -> None:
    if not db.get(Team, team_id):
        raise AppError("NOT_FOUND", "Команда не найдена", 404)


def _version_item(db: DbSession, row) -> dict:
    preview = row.text[:120] + ("…" if len(row.text) > 120 else "")
    return {
        "id": str(row.id),
        "version_no": row.version_no,
        "is_active": row.is_active,
        "text_preview": preview,
        "text": row.text,
        "created_at": row.created_at.isoformat(),
        "created_by_name": creator_name(db, row.created_by),
    }


def _kind_block(db: DbSession, team_id: UUID, kind: str) -> dict:
    ensure_team_prompts(db, team_id)
    versions = list_versions(db, team_id, kind)
    active = next((v for v in versions if v.is_active), None)
    return {
        "current_text": get_active_prompt(db, team_id, kind),
        "active_version_id": str(active.id) if active else None,
        "versions": [_version_item(db, v) for v in versions],
    }


@router.get("/prompts")
def get_team_prompts(
    db: DbSession,
    actor: StaffUser,
    team_id: UUID | None = Query(None),
):
    tid = _resolve_team_id(actor, team_id)
    if not can_manage_team_prompts(actor.user_role, actor.team_id, tid):
        raise AppError("FORBIDDEN", "Нет доступа к промптам этой команды", 403)
    _check_team(db, tid)
    team = db.get(Team, tid)
    ensure_team_prompts(db, tid)
    return {
        "team_id": str(tid),
        "blank_allowance_step_enabled": bool(
            team.blank_allowance_step_enabled if team else False
        ),
        "passport": _kind_block(db, tid, "passport"),
        "technology": _kind_block(db, tid, "technology"),
        "blank_allowance": _kind_block(db, tid, "blank_allowance"),
        "passport_dxf": _kind_block(db, tid, "passport_dxf"),
    }


@router.post("/prompts")
def save_team_prompt(body: PromptSaveRequest, db: DbSession, actor: StaffUser):
    kind = (body.kind or "").strip().lower()
    if kind not in PROMPT_KINDS:
        raise AppError(
            "VALIDATION_ERROR",
            f"kind должен быть одним из: {', '.join(PROMPT_KINDS)}",
            400,
        )
    if not can_manage_team_prompts(actor.user_role, actor.team_id, body.team_id):
        raise AppError("FORBIDDEN", "Нет доступа к промптам этой команды", 403)
    _check_team(db, body.team_id)
    ensure_team_prompts(db, body.team_id, actor.user_id)
    try:
        row = save_new_prompt(db, body.team_id, kind, body.text, actor.user_id)
    except ValueError as e:
        raise AppError("VALIDATION_ERROR", str(e), 400) from e
    db.commit()
    return {"ok": True, "version_id": str(row.id), "version_no": row.version_no}


@router.post("/prompts/restore")
def restore_team_prompt(body: PromptRestoreRequest, db: DbSession, actor: StaffUser):
    if not can_manage_team_prompts(actor.user_role, actor.team_id, body.team_id):
        raise AppError("FORBIDDEN", "Нет доступа к промптам этой команды", 403)
    _check_team(db, body.team_id)
    try:
        row = restore_prompt_version(db, body.team_id, body.version_id, actor.user_id)
    except ValueError as e:
        raise AppError("NOT_FOUND", str(e), 404) from e
    db.commit()
    return {
        "ok": True,
        "kind": row.kind,
        "version_id": str(row.id),
        "version_no": row.version_no,
    }


@router.post("/prompts/apply-default")
def apply_default_team_prompt(body: PromptDefaultRequest, db: DbSession, actor: StaffUser):
    """Активировать встроенный промпт по умолчанию (новая версия)."""
    kind = (body.kind or "").strip().lower()
    if kind not in PROMPT_KINDS:
        raise AppError(
            "VALIDATION_ERROR",
            f"kind должен быть одним из: {', '.join(PROMPT_KINDS)}",
            400,
        )
    if not can_manage_team_prompts(actor.user_role, actor.team_id, body.team_id):
        raise AppError("FORBIDDEN", "Нет доступа к промптам этой команды", 403)
    _check_team(db, body.team_id)
    ensure_team_prompts(db, body.team_id, actor.user_id)
    row = save_new_prompt(
        db, body.team_id, kind, DEFAULT_BY_KIND[kind], actor.user_id
    )
    db.commit()
    return {"ok": True, "version_id": str(row.id), "version_no": row.version_no}


@router.post("/prompts/blank-allowance-step")
def set_blank_allowance_step(
    body: BlankAllowanceStepRequest, db: DbSession, actor: StaffUser
):
    """Включить/выключить опциональный шаг расчёта припусков для команды."""
    if not can_manage_team_prompts(actor.user_role, actor.team_id, body.team_id):
        raise AppError("FORBIDDEN", "Нет доступа к настройкам этой команды", 403)
    team = db.get(Team, body.team_id)
    if not team:
        raise AppError("NOT_FOUND", "Команда не найдена", 404)
    team.blank_allowance_step_enabled = body.enabled
    db.commit()
    return {
        "ok": True,
        "team_id": str(team.id),
        "blank_allowance_step_enabled": team.blank_allowance_step_enabled,
    }
