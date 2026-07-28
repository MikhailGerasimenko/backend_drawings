"""Админка: users, teams, config (superuser + admin)."""
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.config import settings
from app.deps import DbSession, StaffUser, SuperUser, UserCtx
from app.core.exceptions import AppError
from app.models import AppConfig, AuthSession, StatisticsAgg, Team, User
from app.services.ai_config import (
    DEFAULT_MODEL_TEMPERATURE,
    _parse_float_cfg,
    get_ai_verify_ssl,
)
from app.services.operation_catalog import ensure_team_operation_catalog
from app.services.prompts import ensure_team_prompts
from app.roles import (
    ROLE_SUPERUSER,
    ROLE_USER,
    can_change_user_role,
    can_create_role,
    can_disable_user,
    can_manage_user,
    can_reset_password,
    normalize_role,
)
from app.schemas.admin import TeamUpdateRequest, UserAdminPublic, UserUpdateRequest
from app.schemas.auth import TeamPublic
from app.security import generate_random_password, hash_password, make_salt

router = APIRouter(prefix="/admin", tags=["admin"])

MODEL_CONFIG_KEYS = (
    "passportModelBaseUrl",
    "passportModelKey",
    "passportModelModel",
    "technologyModelBaseUrl",
    "technologyModelKey",
    "technologyModelModel",
)


def _cfg_get(db, key: str, default: str = "") -> str:
    row = db.get(AppConfig, key)
    return row.value if row and row.value is not None else default


def _cfg_set(db, key: str, value: str) -> None:
    row = db.get(AppConfig, key)
    if row:
        row.value = value
    else:
        db.add(AppConfig(key=key, value=value))


def _user_admin(db, user: User) -> UserAdminPublic:
    team = db.get(Team, user.team_id) if user.team_id else None
    return UserAdminPublic(
        id=user.id,
        login=user.login,
        display_name=user.display_name,
        role=user.role,
        team_id=user.team_id,
        team_name=team.name if team else None,
        active=user.active,
        created_at=user.created_at,
    )


class ModelEndpointUpdate(BaseModel):
    baseUrl: str | None = None
    apiKey: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)


class ModelConfigUpdate(BaseModel):
    passport: ModelEndpointUpdate | None = None
    technology: ModelEndpointUpdate | None = None
    blank_allowance: ModelEndpointUpdate | None = None
    dxf_passport: ModelEndpointUpdate | None = None
    aiVerifySsl: bool | None = None


@router.get("/users")
def list_users(db: DbSession, _staff: StaffUser):
    users = db.scalars(select(User)).all()
    return {"users": [_user_admin(db, u) for u in users]}


def _require_assignable_team(db: DbSession, team_id: UUID) -> Team:
    """Команда существует и не в архиве — для назначения пользователю."""
    team = db.get(Team, team_id)
    if not team:
        raise AppError("VALIDATION_ERROR", "Укажите существующую команду (team_id)", 400)
    if team.archived:
        raise AppError(
            "VALIDATION_ERROR",
            "Команда архивирована и недоступна для назначения",
            400,
        )
    return team


@router.get("/teams")
def list_teams(db: DbSession, _staff: StaffUser):
    teams = db.scalars(select(Team).order_by(Team.archived, Team.name)).all()
    return {"teams": [TeamPublic.model_validate(t) for t in teams]}


@router.patch("/team")
def update_team(
    body: TeamUpdateRequest,
    db: DbSession,
    _su: SuperUser,
    id: UUID = Query(...),
):
    """Переименование команды — только superuser."""
    team = db.get(Team, id)
    if not team:
        raise AppError("NOT_FOUND", "Команда не найдена", 404)
    if body.name is not None:
        name = str(body.name).strip()
        if not name:
            raise AppError("VALIDATION_ERROR", "Название команды обязательно", 400)
        team.name = name
    db.commit()
    db.refresh(team)
    return TeamPublic.model_validate(team)


@router.post("/team/archive")
def archive_team(db: DbSession, _su: SuperUser, id: UUID = Query(...)):
    """Архив команды, если нет активных пользователей — только superuser."""
    team = db.get(Team, id)
    if not team:
        raise AppError("NOT_FOUND", "Команда не найдена", 404)
    if team.archived:
        return TeamPublic.model_validate(team)
    active_count = db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.team_id == id, User.active.is_(True))
    )
    if active_count:
        raise AppError(
            "VALIDATION_ERROR",
            "Нельзя архивировать команду с активными пользователями",
            400,
        )
    team.archived = True
    db.commit()
    db.refresh(team)
    return TeamPublic.model_validate(team)


@router.post("/teams", status_code=201)
def create_team(body: dict, db: DbSession, actor: StaffUser):
    name = str(body.get("name") or "").strip()
    if not name:
        raise AppError("VALIDATION_ERROR", "Название команды обязательно", 400)
    team = Team(name=name)
    db.add(team)
    db.flush()
    db.add(StatisticsAgg(team_id=team.id))
    ensure_team_prompts(db, team.id, actor.user_id)
    ensure_team_operation_catalog(db, team.id, actor.user_id)
    db.commit()
    db.refresh(team)
    return TeamPublic.model_validate(team)


@router.post("/users", status_code=201)
def create_user(body: dict, db: DbSession, actor: StaffUser):
    login = str(body.get("login") or "").strip().lower()
    password = str(body.get("password") or "")
    display_name = str(body.get("display_name") or login).strip()
    role = normalize_role(body.get("role") or ROLE_USER)
    team_id = body.get("team_id")

    if not can_create_role(actor.user_role, role):
        raise AppError("FORBIDDEN", "Недостаточно прав для назначения этой роли", 403)
    if not login or len(password) < 4:
        raise AppError("VALIDATION_ERROR", "Логин и пароль (мин. 4 символа) обязательны", 400)
    if not team_id:
        raise AppError("VALIDATION_ERROR", "Укажите существующую команду (team_id)", 400)
    _require_assignable_team(db, UUID(str(team_id)))
    if db.scalar(select(User).where(User.login == login)):
        raise AppError("VALIDATION_ERROR", "Логин уже занят", 409)

    salt = make_salt()
    user = User(
        login=login,
        password_hash=hash_password(password, salt),
        salt=salt,
        display_name=display_name,
        role=role,
        team_id=UUID(str(team_id)),
        active=body.get("active", True) is not False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_admin(db, user)


@router.patch("/user")
def update_user(
    body: UserUpdateRequest,
    db: DbSession,
    actor: StaffUser,
    id: UUID = Query(...),
):
    target = db.get(User, id)
    if not target:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)
    if not can_manage_user(actor.user_role, target.role):
        raise AppError("FORBIDDEN", "Недостаточно прав для изменения этого пользователя", 403)

    data = body.model_dump(exclude_unset=True)
    if "display_name" in data:
        name = str(data["display_name"] or "").strip()
        if not name:
            raise AppError("VALIDATION_ERROR", "Имя не может быть пустым", 400)
        target.display_name = name
    if "team_id" in data and data["team_id"] is not None:
        _require_assignable_team(db, data["team_id"])
        target.team_id = data["team_id"]
    if "role" in data and data["role"] is not None:
        new_role = normalize_role(data["role"])
        if new_role != target.role and not can_change_user_role(
            actor.user_role, target.role, new_role
        ):
            raise AppError("FORBIDDEN", "Недостаточно прав для назначения этой роли", 403)
        target.role = new_role

    db.commit()
    db.refresh(target)
    return _user_admin(db, target)


@router.post("/user/reset-password")
def reset_user_password(
    db: DbSession,
    actor: StaffUser,
    id: UUID = Query(...),
):
    """Сброс пароля: генерируется случайный пароль, возвращается один раз в ответе."""
    target = db.get(User, id)
    if not target:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)
    if target.id == actor.user_id:
        raise AppError(
            "VALIDATION_ERROR",
            "Свой пароль меняйте в личном кабинете",
            400,
        )
    if not can_reset_password(actor.user_role, target.role):
        raise AppError("FORBIDDEN", "Недостаточно прав для сброса пароля", 403)

    new_password = generate_random_password()
    salt = make_salt()
    target.salt = salt
    target.password_hash = hash_password(new_password, salt)
    for sess in db.scalars(select(AuthSession).where(AuthSession.user_id == id)).all():
        db.delete(sess)
    db.commit()
    return {"ok": True, "generated_password": new_password}


@router.delete("/user")
def disable_user(db: DbSession, actor: StaffUser, id: UUID = Query(...)):
    target = db.get(User, id)
    if not target:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)
    if not can_disable_user(actor.user_role, target.role, target.id, actor.user_id):
        raise AppError(
            "FORBIDDEN",
            "Нельзя отключить этого пользователя (суперпользователь защищён, админов — только superuser)",
            403,
        )
    target.active = False
    for sess in db.scalars(select(AuthSession).where(AuthSession.user_id == id)).all():
        db.delete(sess)
    db.commit()
    return {"ok": True}


@router.post("/user/restore")
def restore_user(db: DbSession, actor: StaffUser, id: UUID = Query(...)):
    target = db.get(User, id)
    if not target:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)
    if target.role == ROLE_SUPERUSER and actor.user_role != ROLE_SUPERUSER:
        raise AppError("FORBIDDEN", "Только superuser управляет суперпользователями", 403)
    if not can_manage_user(actor.user_role, target.role):
        raise AppError("FORBIDDEN", "Недостаточно прав", 403)
    target.active = True
    db.commit()
    return _user_admin(db, target)


@router.delete("/user/purge")
def purge_user(db: DbSession, actor: SuperUser, id: UUID = Query(...)):
    """Полное удаление пользователя — только superuser, нельзя удалить себя или другого superuser."""
    target = db.get(User, id)
    if not target:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)
    if target.id == actor.user_id:
        raise AppError("FORBIDDEN", "Нельзя удалить собственную учётную запись", 403)
    if target.role == ROLE_SUPERUSER:
        raise AppError("FORBIDDEN", "Нельзя удалить суперпользователя", 403)
    for sess in db.scalars(select(AuthSession).where(AuthSession.user_id == id)).all():
        db.delete(sess)
    db.delete(target)
    db.commit()
    return {"ok": True}


def _endpoint_public(
    db: DbSession, base_key: str, key_key: str, model_key: str, temp_key: str
) -> dict:
    key = _cfg_get(db, key_key)
    return {
        "baseUrl": _cfg_get(db, base_key, settings.openrouter_base_url),
        "model": _cfg_get(db, model_key, settings.ai_model),
        "temperature": _parse_float_cfg(
            _cfg_get(db, temp_key), DEFAULT_MODEL_TEMPERATURE
        ),
        "apiKeySet": bool(key),
        "apiKeyHint": ("***" + key[-4:]) if key else "—",
    }


@router.get("/model-config")
def get_model_config(db: DbSession, _su: SuperUser):
    """Параметры подключения к модели — только superuser."""
    return {
        "passport": _endpoint_public(
            db,
            "passportModelBaseUrl",
            "passportModelKey",
            "passportModelModel",
            "passportModelTemperature",
        ),
        "technology": _endpoint_public(
            db,
            "technologyModelBaseUrl",
            "technologyModelKey",
            "technologyModelModel",
            "technologyModelTemperature",
        ),
        "blank_allowance": _endpoint_public(
            db,
            "blankAllowanceModelBaseUrl",
            "blankAllowanceModelKey",
            "blankAllowanceModelModel",
            "blankAllowanceModelTemperature",
        ),
        "dxf_passport": _endpoint_public(
            db,
            "dxfPassportModelBaseUrl",
            "dxfPassportModelKey",
            "dxfPassportModelModel",
            "dxfPassportModelTemperature",
        ),
        "aiVerifySsl": get_ai_verify_ssl(db),
    }



def _apply_endpoint(db, prefix: str, data: ModelEndpointUpdate) -> None:
    if data.baseUrl is not None and str(data.baseUrl).strip():
        _cfg_set(db, f"{prefix}ModelBaseUrl", str(data.baseUrl).strip())
    if data.model is not None and str(data.model).strip():
        _cfg_set(db, f"{prefix}ModelModel", str(data.model).strip())
    if data.temperature is not None:
        _cfg_set(db, f"{prefix}ModelTemperature", str(data.temperature))
    if data.apiKey is not None:
        key_name = f"{prefix}ModelKey"
        if data.apiKey == "":
            row = db.get(AppConfig, key_name)
            if row:
                db.delete(row)
        elif str(data.apiKey).strip():
            _cfg_set(db, key_name, str(data.apiKey).strip())


@router.post("/model-config")
@router.patch("/model-config")
def update_model_config(body: ModelConfigUpdate, db: DbSession, _su: SuperUser):
    if body.passport:
        _apply_endpoint(db, "passport", body.passport)
    if body.technology:
        _apply_endpoint(db, "technology", body.technology)
    if body.blank_allowance:
        _apply_endpoint(db, "blankAllowance", body.blank_allowance)
    if body.dxf_passport:
        _apply_endpoint(db, "dxfPassport", body.dxf_passport)
    if body.aiVerifySsl is not None:
        _cfg_set(db, "aiVerifySsl", "true" if body.aiVerifySsl else "false")
    db.commit()
    return {"ok": True}


# Алиасы по контракту / tasks T027 (то же, что model-config)
@router.get("/config")
def get_config(db: DbSession, _su: SuperUser):
    return get_model_config(db, _su)


@router.post("/config")
@router.patch("/config")
def update_config(body: ModelConfigUpdate, db: DbSession, _su: SuperUser):
    return update_model_config(body, db, _su)
