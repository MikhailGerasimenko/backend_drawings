"""Справочник операций по командам."""
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OperationCatalogEntry, utcnow
from app.schema_modules.operation_catalog_defaults import DEFAULT_OPERATION_CATALOG


def ensure_team_operation_catalog(
    db: Session, team_id: UUID, created_by: UUID | None = None
) -> None:
    """Заполнить справочник по умолчанию, если пуст."""
    exists = db.scalar(
        select(OperationCatalogEntry.id)
        .where(OperationCatalogEntry.team_id == team_id)
        .limit(1)
    )
    if exists:
        return
    for i, (operation, equipment) in enumerate(DEFAULT_OPERATION_CATALOG):
        db.add(
            OperationCatalogEntry(
                team_id=team_id,
                operation=operation,
                equipment=equipment,
                sort_order=i,
                created_by=created_by,
                created_at=utcnow(),
            )
        )
    db.flush()


def list_catalog(db: Session, team_id: UUID) -> list[OperationCatalogEntry]:
    ensure_team_operation_catalog(db, team_id)
    return list(
        db.scalars(
            select(OperationCatalogEntry)
            .where(OperationCatalogEntry.team_id == team_id)
            .order_by(OperationCatalogEntry.sort_order, OperationCatalogEntry.operation)
        ).all()
    )


def catalog_entry_dict(row: OperationCatalogEntry) -> dict:
    return {
        "id": str(row.id),
        "operation": row.operation,
        "equipment": row.equipment,
        "sort_order": row.sort_order,
    }


def replace_team_catalog(
    db: Session,
    team_id: UUID,
    entries: list[dict],
    user_id: UUID | None,
) -> list[OperationCatalogEntry]:
    """Синхронизация справочника: сохраняет id существующих строк, новые — без id."""
    existing = {r.id: r for r in list_catalog(db, team_id)}
    incoming_ids: set[UUID] = set()
    pending_updates: list[tuple[OperationCatalogEntry, str, str, int]] = []
    out: list[OperationCatalogEntry] = []

    for i, item in enumerate(entries):
        op = (item.get("operation") or "").strip()
        eq = (item.get("equipment") or "").strip()
        if not op or not eq:
            raise ValueError("Операция и оборудование обязательны")

        raw_id = item.get("id")
        if raw_id:
            cid = UUID(str(raw_id))
            if cid in incoming_ids:
                raise ValueError(f"Дубликат id в справочнике: {cid}")
            incoming_ids.add(cid)
            row = existing.get(cid)
            if not row:
                raise ValueError(f"Операция не найдена в справочнике: {cid}")
            # Временные значения — иначе unique (team_id, operation, equipment) ломается при перестановке пар
            row.operation = f"__sync_{uuid4().hex}__"
            row.equipment = f"__sync_{uuid4().hex}__"
            pending_updates.append((row, op, eq, i))
            out.append(row)
        else:
            row = OperationCatalogEntry(
                team_id=team_id,
                operation=op,
                equipment=eq,
                sort_order=i,
                created_by=user_id,
                created_at=utcnow(),
            )
            db.add(row)
            out.append(row)

    if pending_updates:
        db.flush()
        for row, op, eq, sort_order in pending_updates:
            row.operation = op
            row.equipment = eq
            row.sort_order = sort_order

    for rid, row in existing.items():
        if rid not in incoming_ids:
            db.delete(row)

    db.flush()
    return out


def resolve_selected_operations(
    db: Session, team_id: UUID, catalog_ids: list[UUID]
) -> list[dict]:
    """Проверить id и вернуть список для сессии и LLM."""
    if not catalog_ids:
        raise ValueError("Выберите хотя бы одну операцию")
    rows = list_catalog(db, team_id)
    by_id = {r.id: r for r in rows}
    seen: set[UUID] = set()
    out: list[dict] = []
    for cid in catalog_ids:
        if cid in seen:
            continue
        row = by_id.get(cid)
        if not row:
            raise ValueError(f"Операция не найдена в справочнике: {cid}")
        seen.add(cid)
        out.append(
            {
                "catalog_id": str(row.id),
                "operation": row.operation,
                "equipment": row.equipment,
            }
        )
    return out
