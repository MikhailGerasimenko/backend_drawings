"""Архив и переименование команд (superuser)."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Team, User
from app.security import hash_password, make_salt

client = TestClient(app)


def _login(login, password):
    r = client.post("/api/v1/auth/login", json={"login": login, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def super_headers():
    return _login("admin", "admin")


def test_team_rename_and_archive(super_headers):
    r = client.post(
        "/api/v1/admin/teams",
        headers=super_headers,
        json={"name": "Команда для архива тест"},
    )
    assert r.status_code == 201
    team_id = r.json()["id"]
    assert r.json()["archived"] is False

    r = client.patch(
        f"/api/v1/admin/team?id={team_id}",
        headers=super_headers,
        json={"name": "Переименованная команда"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Переименованная команда"

    r = client.post(f"/api/v1/admin/team/archive?id={team_id}", headers=super_headers)
    assert r.status_code == 200
    assert r.json()["archived"] is True

    teams = client.get("/api/v1/admin/teams", headers=super_headers).json()["teams"]
    archived = next(t for t in teams if t["id"] == team_id)
    assert archived["archived"] is True


def test_cannot_assign_archived_team(super_headers):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        team = Team(name="Архивная для assign", archived=True)
        db.add(team)
        db.commit()
        db.refresh(team)
        team_id = str(team.id)
    finally:
        db.close()

    login = "archived_team_" + uuid.uuid4().hex[:8]
    r = client.post(
        "/api/v1/admin/users",
        headers=super_headers,
        json={
            "login": login,
            "password": "secret",
            "display_name": "Test",
            "team_id": team_id,
            "role": "user",
        },
    )
    assert r.status_code == 400
    assert "архив" in r.json()["error"]["message"].lower()


def test_cannot_archive_team_with_active_users(super_headers):
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        team = Team(name="С активными пользователями")
        db.add(team)
        db.flush()
        salt = make_salt()
        user = User(
            login="active_in_team_" + uuid.uuid4().hex[:8],
            password_hash=hash_password("secret", salt),
            salt=salt,
            display_name="U",
            role="user",
            team_id=team.id,
            active=True,
        )
        db.add(user)
        db.commit()
        team_id = str(team.id)
    finally:
        db.close()

    r = client.post(
        f"/api/v1/admin/team/archive?id={team_id}",
        headers=super_headers,
    )
    assert r.status_code == 400
    assert "активн" in r.json()["error"]["message"].lower()
