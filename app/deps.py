"""Зависимости FastAPI: БД, текущий пользователь."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.exceptions import AppError
from app.models import AuthSession, User
from app.roles import ROLE_SUPERUSER, can_access_admin_panel
DbSession = Annotated[Session, Depends(get_db)]


@dataclass
class UserCtx:
    user_id: UUID
    team_id: UUID
    user_name: str
    user_role: str
    token: str


def _parse_bearer(authorization: str | None, x_session_token: str | None) -> str:
    auth = authorization or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (x_session_token or "").strip()


def get_current_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
) -> UserCtx:
    token = _parse_bearer(authorization, x_session_token)
    if not token:
        raise AppError("UNAUTHORIZED", "Требуется авторизация", 401)

    sess = db.get(AuthSession, token)
    exp = sess.expires_at if sess else None
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if not sess or not exp or exp < datetime.now(timezone.utc):
        raise AppError("UNAUTHORIZED", "Сессия истекла — войдите снова", 401)

    user = db.get(User, sess.user_id)
    if not user or not user.active:
        raise AppError("UNAUTHORIZED", "Пользователь отключён", 401)

    team_id = sess.team_id or user.team_id
    if not team_id:
        raise AppError("VALIDATION_ERROR", "Пользователю не назначена команда", 403)

    return UserCtx(
        user_id=user.id,
        team_id=team_id,
        user_name=user.display_name or user.login,
        user_role=user.role or "user",
        token=token,
    )


def require_staff(ctx: Annotated[UserCtx, Depends(get_current_user)]) -> UserCtx:
    """Доступ к админке: superuser и admin."""
    if not can_access_admin_panel(ctx.user_role):
        raise AppError("FORBIDDEN", "Доступ только для администратора", 403)
    return ctx


def require_superuser(ctx: Annotated[UserCtx, Depends(get_current_user)]) -> UserCtx:
    if ctx.user_role != ROLE_SUPERUSER:
        raise AppError("FORBIDDEN", "Доступ только для суперпользователя", 403)
    return ctx


CurrentUser = Annotated[UserCtx, Depends(get_current_user)]
StaffUser = Annotated[UserCtx, Depends(require_staff)]
SuperUser = Annotated[UserCtx, Depends(require_superuser)]
# обратная совместимость имён
AdminUser = StaffUser
