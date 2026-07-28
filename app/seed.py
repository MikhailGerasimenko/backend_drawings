"""Начальные данные: команда + superuser (если БД пустая)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bootstrap import ensure_bootstrap_superuser
from app.core.config import settings
from app.models import StatisticsAgg, Team, User
from app.services.operation_catalog import ensure_team_operation_catalog
from app.services.prompts import ensure_team_prompts
from app.roles import ROLE_SUPERUSER
from app.security import hash_password, make_salt


def seed_db(db: Session) -> None:
    if db.scalar(select(User.id).limit(1)):
        ensure_bootstrap_superuser(db)
        for team in db.scalars(select(Team)).all():
            ensure_team_prompts(db, team.id)
            ensure_team_operation_catalog(db, team.id)
        db.commit()
        return

    team = Team(name="Команда по умолчанию")
    db.add(team)
    db.flush()

    salt = make_salt()
    admin = User(
        login=settings.bootstrap_admin_login.lower(),
        password_hash=hash_password(settings.bootstrap_admin_password, salt),
        salt=salt,
        display_name="Суперпользователь",
        role=ROLE_SUPERUSER,
        team_id=team.id,
        active=True,
    )
    db.add(admin)
    db.add(
        StatisticsAgg(
            team_id=team.id,
            sessions_total=0,
            remarks_passport_total=0,
            remarks_technology_total=0,
            total_duration_sec=0,
        )
    )
    ensure_team_prompts(db, team.id, admin.id)
    ensure_team_operation_catalog(db, team.id, admin.id)
    db.commit()
