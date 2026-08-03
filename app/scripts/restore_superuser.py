"""
Восстановить bootstrap-учётку (active + role=superuser).
Запуск: docker compose exec backend python -m app.scripts.restore_superuser
"""
from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models import Team, User
from app.roles import ROLE_SUPERUSER
from app.security import hash_password, make_salt


def main() -> None:
    login = settings.bootstrap_admin_login.lower()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.login == login))
        if not user:
            team = db.scalar(select(Team).limit(1))
            if not team:
                team = Team(name="Команда по умолчанию")
                db.add(team)
                db.flush()
            salt = make_salt()
            user = User(
                login=login,
                password_hash=hash_password(settings.bootstrap_admin_password, salt),
                salt=salt,
                display_name="Суперпользователь",
                role=ROLE_SUPERUSER,
                team_id=team.id,
                active=True,
            )
            db.add(user)
            print(f"Создан superuser: {login}")
        else:
            user.active = True
            user.role = ROLE_SUPERUSER
            print(f"Восстановлен: {login} (active=True, role=superuser)")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
