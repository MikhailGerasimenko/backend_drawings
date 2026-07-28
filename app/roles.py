"""Роли: superuser, admin, user — права доступа."""

ROLE_SUPERUSER = "superuser"
ROLE_ADMIN = "admin"
ROLE_USER = "user"

STAFF_ROLES = frozenset({ROLE_SUPERUSER, ROLE_ADMIN})
ALL_ROLES = frozenset({ROLE_SUPERUSER, ROLE_ADMIN, ROLE_USER})


def is_staff(role: str) -> bool:
    return role in STAFF_ROLES


def is_superuser(role: str) -> bool:
    return role == ROLE_SUPERUSER


def normalize_role(role: str | None) -> str:
    r = (role or ROLE_USER).lower()
    return r if r in ALL_ROLES else ROLE_USER


def can_access_admin_panel(role: str) -> bool:
    return is_staff(role)


def can_disable_user(actor_role: str, target_role: str, target_id, actor_id) -> bool:
    """Суперпользователь не отключается; админов — только superuser."""
    if target_id == actor_id:
        return False
    if target_role == ROLE_SUPERUSER:
        return False
    if target_role == ROLE_ADMIN:
        return actor_role == ROLE_SUPERUSER
    return is_staff(actor_role)


def can_create_role(actor_role: str, new_role: str) -> bool:
    if new_role not in ALL_ROLES:
        return False
    if actor_role == ROLE_SUPERUSER:
        return True
    if actor_role == ROLE_ADMIN:
        return new_role == ROLE_USER
    return False


def can_modify_session(actor_role: str, actor_id, session_created_by) -> bool:
    """user — только свои сессии; staff — любые в команде."""
    if is_staff(actor_role):
        return True
    return session_created_by == actor_id


def can_manage_user(actor_role: str, target_role: str) -> bool:
    """Редактирование полей пользователя в админке."""
    if target_role == ROLE_SUPERUSER:
        return actor_role == ROLE_SUPERUSER
    if target_role == ROLE_ADMIN:
        return actor_role == ROLE_SUPERUSER
    return is_staff(actor_role)


def can_reset_password(actor_role: str, target_role: str) -> bool:
    """Сброс пароля: admin — user; superuser — user и admin."""
    if target_role == ROLE_SUPERUSER:
        return actor_role == ROLE_SUPERUSER
    if target_role == ROLE_ADMIN:
        return actor_role == ROLE_SUPERUSER
    return is_staff(actor_role)


def can_manage_team_prompts(actor_role: str, actor_team_id, requested_team_id) -> bool:
    """Промпты: admin — только своя команда; superuser — любая."""
    if actor_role == ROLE_SUPERUSER:
        return True
    if actor_role == ROLE_ADMIN:
        return str(actor_team_id) == str(requested_team_id)
    return False


def can_change_user_role(actor_role: str, target_role: str, new_role: str) -> bool:
    if not can_create_role(actor_role, new_role):
        return False
    if target_role == ROLE_SUPERUSER and actor_role != ROLE_SUPERUSER:
        return False
    if target_role == ROLE_ADMIN and actor_role != ROLE_SUPERUSER:
        return False
    return True
