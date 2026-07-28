"""Гарантия активного superuser при старте (bootstrap login)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import StatisticsAgg, Team, User
from app.roles import ROLE_SUPERUSER
from app.security import hash_password, make_salt


def ensure_bootstrap_superuser(db: Session) -> None:
    """Восстанавливает учётку из BOOTSTRAP_ADMIN_* если она отключена."""
    login = settings.bootstrap_admin_login.lower()
    user = db.scalar(select(User).where(User.login == login))
    if user:
        changed = False
        if not user.active:
            user.active = True
            changed = True
        if user.role != ROLE_SUPERUSER:
            user.role = ROLE_SUPERUSER
            changed = True
        if changed:
            db.commit()
        return

    if db.scalar(select(User.id).limit(1)):
        return

    team = Team(name="Команда по умолчанию")
    db.add(team)
    db.flush()
    salt = make_salt()
    db.add(
        User(
            login=login,
            password_hash=hash_password(settings.bootstrap_admin_password, salt),
            salt=salt,
            display_name="Суперпользователь",
            role=ROLE_SUPERUSER,
            team_id=team.id,
            active=True,
        )
    )
    db.add(
        StatisticsAgg(
            team_id=team.id,
            sessions_total=0,
            remarks_passport_total=0,
            remarks_technology_total=0,
            total_duration_sec=0,
        )
    )
    db.commit()
