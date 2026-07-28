"""Общие шаги сессии для pytest (выбор операций перед технологией)."""
import time

from fastapi.testclient import TestClient


def generate_technology_with_catalog(client: TestClient, headers: dict, sid: str) -> None:
    r = client.get("/api/v1/operation-catalog", headers=headers)
    assert r.status_code == 200, r.text
    entries = r.json().get("entries") or []
    assert entries, "Справочник операций пуст"
    ids = [entries[0]["id"]]
    if len(entries) > 1:
        ids.append(entries[1]["id"])
    r = client.post(
        f"/api/v1/session/technology/generate?id={sid}",
        json={"catalog_ids": ids},
        headers=headers,
    )
    assert r.status_code == 202, r.text


def session_at_technology_review(client: TestClient, headers: dict, sid: str) -> dict:
    client.post(f"/api/v1/session/passport/approve?id={sid}", headers=headers)
    generate_technology_with_catalog(client, headers, sid)
    body = None
    for _ in range(30):
        r = client.get(f"/api/v1/session?id={sid}", headers=headers)
        assert r.status_code == 200
        body = r.json()
        if body["status"] == "technology_review":
            return body
        if body["status"] in ("technology_failed", "failed"):
            break
        time.sleep(0.05)
    assert body and body["status"] == "technology_review", body.get("status") if body else None
    return body
