"""US3: доля полей, принятых без замечаний (FR-018/FR-019)."""
from app.models import WorkSession
from app.services.document_diff import KIND_ARTIFACT
from app.services.field_stats import compute_stage_acceptance, snapshot_stage_acceptance

_APPROVED = {
    "blank": {
        "source_stock": "Прокат 50",
        "pre_heat_treatment": "Точение черновое",
        "pre_finish_machining": "Под закалку",
    },
    "allowances": {"summary": "Припуск 2 мм"},
    "confirmation_required": False,
}


def _session_with_history(first: dict | None) -> WorkSession:
    s = WorkSession(title="t", status="blank_allowance_review")
    s.blank_allowance = _APPROVED
    if first is not None:
        s.llm_history = {"blank_allowance": [{"kind": KIND_ARTIFACT, "content": first}]}
    return s


def test_acceptance_full_when_no_history():
    # Нет истории правок → первая версия = согласованная → 100% принятия
    s = _session_with_history(None)
    res = compute_stage_acceptance(s, "blank_allowance")
    assert res == {"total": 5, "unchanged": 5, "share_pct": 100.0}


def test_acceptance_counts_changed_field():
    # Один из пяти полей отличается от первой версии → 80%
    first = {
        "blank": {
            "source_stock": "Прокат 40",  # отличается
            "pre_heat_treatment": "Точение черновое",
            "pre_finish_machining": "Под закалку",
        },
        "allowances": {"summary": "Припуск 2 мм"},
        "confirmation_required": False,
    }
    s = _session_with_history(first)
    res = compute_stage_acceptance(s, "blank_allowance")
    assert res["total"] == 5
    assert res["unchanged"] == 4
    assert res["share_pct"] == 80.0


def test_snapshot_writes_into_field_acceptance():
    s = _session_with_history(None)
    snapshot_stage_acceptance(s, "blank_allowance")
    assert "blank_allowance" in s.field_acceptance
    assert s.field_acceptance["blank_allowance"]["share_pct"] == 100.0
