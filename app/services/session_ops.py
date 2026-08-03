"""Флаг пропуска выбора операций и синхронизация маршрута со справочником."""
import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import WorkSession
from app.services.operation_catalog import catalog_entry_dict, list_catalog


def session_operations_skipped(s: WorkSession) -> bool:
    """True, если пользователь пропустил ручной выбор (последнее — operations_skipped)."""
    last_sel = -1
    last_skip = -1
    for i, ev in enumerate(s.events or []):
        t = ev.get("type")
        if t == "operations_selected":
            last_sel = i
        elif t == "operations_skipped":
            last_skip = i
    return last_skip >= 0 and last_skip > last_sel


def format_catalog_system_block(db: Session, team_id: UUID) -> str:
    """JSON справочника для system prompt при пропуске выбора."""
    entries = [catalog_entry_dict(r) for r in list_catalog(db, team_id)]
    return json.dumps(entries, ensure_ascii=False, indent=2)


def sync_selected_operations_from_route(
    db: Session, team_id: UUID, route: list
) -> list[dict]:
    """Сопоставить шаги route с записями справочника (после генерации технологии)."""
    rows = list_catalog(db, team_id)
    lookup: dict[tuple[str, str], object] = {}
    for r in rows:
        lookup[(r.operation.strip().lower(), r.equipment.strip().lower())] = r

    out: list[dict] = []
    seen: set[str] = set()
    for step in route or []:
        if not isinstance(step, dict):
            continue
        name = (step.get("name") or "").strip().lower()
        eq = (step.get("equipment") or "").strip().lower()
        row = lookup.get((name, eq))
        if not row and name:
            partial = [
                r
                for r in rows
                if name in r.operation.strip().lower()
                or r.operation.strip().lower() in name
            ]
            if eq:
                by_eq = [r for r in partial if r.equipment.strip().lower() == eq]
                partial = by_eq or partial
            row = partial[0] if partial else None
        if not row:
            continue
        cid = str(row.id)
        if cid in seen:
            continue
        seen.add(cid)
        out.append(
            {
                "catalog_id": cid,
                "operation": row.operation,
                "equipment": row.equipment,
            }
        )
    return out
