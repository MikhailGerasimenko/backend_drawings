"""POST /auth/login, /auth/logout, GET /auth/me"""
from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.core.exceptions import AppError
from app.models import AuthSession, Team, User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, LoginResponse, TeamPublic, UserPublic
from app.security import hash_password, make_salt, new_token, token_expires_at, verify_password
from app.services.user_audit import log_action

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: DbSession):
    login_name = body.login.strip().lower()
    if not login_name or not body.password:
        raise AppError("VALIDATION_ERROR", "Логин и пароль обязательны", 400)

    user = db.scalar(select(User).where(User.login == login_name, User.active.is_(True)))
    if not user or not verify_password(body.password, user.salt, user.password_hash):
        raise AppError("UNAUTHORIZED", "Неверный логин или пароль", 401)

    team = db.get(Team, user.team_id) if user.team_id else None
    if not team:
        raise AppError("FORBIDDEN", "Команда не назначена — обратитесь к администратору", 403)

    token = new_token()
    db.add(
        AuthSession(
            token=token,
            user_id=user.id,
            team_id=team.id,
            expires_at=token_expires_at(),
        )
    )
    log_action(
        db,
        user_id=user.id,
        team_id=team.id,
        action_type="login",
        status="success",
    )
    db.commit()

    return LoginResponse(
        token=token,
        user=UserPublic.model_validate(user),
        team=TeamPublic.model_validate(team),
    )


@router.post("/logout")
def logout(db: DbSession, user: CurrentUser):
    log_action(
        db,
        user_id=user.user_id,
        team_id=user.team_id,
        action_type="logout",
        status="success",
    )
    sess = db.get(AuthSession, user.token)
    if sess:
        db.delete(sess)
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(db: DbSession, user: CurrentUser):
    u = db.get(User, user.user_id)
    team = db.get(Team, user.team_id)
    return {"user": UserPublic.model_validate(u), "team": TeamPublic.model_validate(team)}


def _validate_new_password(new_password: str, password_confirm: str) -> None:
    if len(new_password) < 4:
        raise AppError("VALIDATION_ERROR", "Новый пароль — минимум 4 символа", 400)
    if new_password != password_confirm:
        raise AppError("VALIDATION_ERROR", "Пароли не совпадают", 400)


@router.post("/change-password")
def change_password(body: ChangePasswordRequest, db: DbSession, user: CurrentUser):
    """Смена своего пароля (все роли)."""
    _validate_new_password(body.new_password, body.password_confirm)
    u = db.get(User, user.user_id)
    if not u:
        raise AppError("NOT_FOUND", "Пользователь не найден", 404)
    if not verify_password(body.old_password, u.salt, u.password_hash):
        raise AppError("UNAUTHORIZED", "Неверный текущий пароль", 401)
    salt = make_salt()
    u.salt = salt
    u.password_hash = hash_password(body.new_password, salt)
    db.commit()
    return {"ok": True}
