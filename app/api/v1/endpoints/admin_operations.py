"""Админка: справочник операций по команде."""
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.deps import DbSession, StaffUser
from app.core.exceptions import AppError
from app.models import Team
from app.roles import ROLE_SUPERUSER, can_manage_team_prompts
from app.services.operation_catalog import (
    catalog_entry_dict,
    ensure_team_operation_catalog,
    list_catalog,
    replace_team_catalog,
)

router = APIRouter(prefix="/admin", tags=["admin-operations"])


class OperationCatalogEntryInput(BaseModel):
    id: UUID | None = None
    operation: str = Field(min_length=1, max_length=255)
    equipment: str = Field(min_length=1, max_length=255)


class OperationCatalogReplaceRequest(BaseModel):
    team_id: UUID
    entries: list[OperationCatalogEntryInput]


def _resolve_team_id(actor: StaffUser, team_id: UUID | None) -> UUID:
    if actor.user_role == ROLE_SUPERUSER:
        if not team_id:
            raise AppError("VALIDATION_ERROR", "Укажите team_id", 400)
        return team_id
    if team_id and team_id != actor.team_id:
        raise AppError("FORBIDDEN", "Доступ только к справочнику своей команды", 403)
    return actor.team_id


def _check_team(db: DbSession, team_id: UUID) -> None:
    if not db.get(Team, team_id):
        raise AppError("NOT_FOUND", "Команда не найдена", 404)


@router.get("/operation-catalog")
def get_operation_catalog(
    db: DbSession,
    actor: StaffUser,
    team_id: UUID | None = Query(None),
):
    tid = _resolve_team_id(actor, team_id)
    if not can_manage_team_prompts(actor.user_role, actor.team_id, tid):
        raise AppError("FORBIDDEN", "Нет доступа к справочнику этой команды", 403)
    _check_team(db, tid)
    rows = list_catalog(db, tid)
    return {
        "team_id": str(tid),
        "entries": [catalog_entry_dict(r) for r in rows],
    }


@router.put("/operation-catalog")
def put_operation_catalog(
    body: OperationCatalogReplaceRequest,
    db: DbSession,
    actor: StaffUser,
):
    if not can_manage_team_prompts(actor.user_role, actor.team_id, body.team_id):
        raise AppError("FORBIDDEN", "Нет доступа к справочнику этой команды", 403)
    _check_team(db, body.team_id)
    try:
        rows = replace_team_catalog(
            db,
            body.team_id,
            [e.model_dump() for e in body.entries],
            actor.user_id,
        )
    except ValueError as e:
        raise AppError("VALIDATION_ERROR", str(e), 400) from e
    db.commit()
    return {
        "ok": True,
        "entries": [catalog_entry_dict(r) for r in rows],
    }
