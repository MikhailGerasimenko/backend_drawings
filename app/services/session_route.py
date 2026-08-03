"""Переход сессии после выбора/подбора маршрута операций."""
from sqlalchemy.orm import Session

from app.models import Team, WorkSession, utcnow
from app.services.llm_history import reset_stage


def ops_catalog_ids(selected: list) -> list[str]:
    return sorted(str(x.get("catalog_id") or "") for x in (selected or []))


def invalidate_blank_on_route_change(s: WorkSession, new_selected: list) -> None:
    """FR-049: смена состава маршрута после согласования расчёта — сброс."""
    if not s.blank_allowance_approved:
        return
    if ops_catalog_ids(s.selected_operations or []) != ops_catalog_ids(new_selected):
        s.blank_allowance = None
        s.blank_allowance_approved = False


def apply_operations_route(db: Session, s: WorkSession, selected: list[dict]) -> None:
    """Записать маршрут и перевести сессию к расчёту припусков или технологии."""
    route_changed = bool(s.selected_operations) and (
        ops_catalog_ids(s.selected_operations) != ops_catalog_ids(selected)
    )
    invalidate_blank_on_route_change(s, selected)
    s.selected_operations = selected
    if route_changed:
        reset_stage(s, "technology")
        reset_stage(s, "blank_allowance")
    team = db.get(Team, s.team_id)
    step_on = bool(team and team.blank_allowance_step_enabled)
    s.blank_allowance_step_active = step_on
    if step_on:
        s.blank_allowance = None
        s.blank_allowance_approved = False
    s.status = "generating_blank_allowance" if step_on else "generating_technology"
    s.updated_at = utcnow()


def advance_after_operations_skipped(db: Session, s: WorkSession) -> None:
    """Пропуск выбора: сразу расчёт припусков или технология; маршрут определит LLM."""
    s.selected_operations = []
    team = db.get(Team, s.team_id)
    step_on = bool(team and team.blank_allowance_step_enabled)
    s.blank_allowance_step_active = step_on
    if step_on:
        s.blank_allowance = None
        s.blank_allowance_approved = False
    s.status = "generating_blank_allowance" if step_on else "generating_technology"
    s.updated_at = utcnow()
