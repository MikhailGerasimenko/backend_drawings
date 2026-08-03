"""T031: smoke auth + sessions list."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_me_logout():
    r = client.post(
        "/api/v1/auth/login",
        json={"login": "admin", "password": "admin"},
    )
    assert r.status_code == 200
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    r = client.get("/api/v1/auth/me", headers=h)
    assert r.status_code == 200
    assert r.json()["user"]["login"] == "admin"

    r = client.get("/api/v1/sessions", headers=h)
    assert r.status_code == 200
    assert "sessions" in r.json()

    r = client.post("/api/v1/auth/logout", headers=h)
    assert r.status_code == 200

    r = client.get("/api/v1/sessions", headers=h)
    assert r.status_code == 401
