"""Unit-тесты вычисления diff полей между версиями документа — specs/006 (US1)."""
from types import SimpleNamespace

from app.services.document_diff import (
    compute_field_diffs,
    previous_artifact,
    stage_field_diffs,
)


def _passport(part_type, designation="ОБ-1"):
    return {
        "schema_version": "2.0",
        "part_type": {"value": part_type, "missing_on_drawing": part_type is None},
        "designation": {"value": designation, "missing_on_drawing": False},
    }


def test_single_passport_field_change():
    diffs = {
        d["field"]: d
        for d in compute_field_diffs(
            _passport("Тело вращения"), _passport("Толкатель"), "passport"
        )
    }
    assert diffs["part_type"]["old"] == "Тело вращения"
    assert diffs["part_type"]["new"] == "Толкатель"
    # неизменённое поле не попадает в diff
    assert "designation" not in diffs


def test_no_diff_on_first_version():
    # одна artifact-версия в истории → предыдущей нет → diff пуст (FR-017)
    s = SimpleNamespace(
        llm_history={
            "passport": [{"kind": "artifact", "content": _passport("Вал")}]
        },
        passport=_passport("Вал"),
    )
    assert previous_artifact(s, "passport") is None
    assert stage_field_diffs(s, "passport") == []


def test_missing_to_value_diff():
    prev = {
        "schema_version": "2.0",
        "part_type": {"value": None, "missing_on_drawing": True},
        "designation": {"value": "ОБ-1", "missing_on_drawing": False},
    }
    diffs = {d["field"]: d for d in compute_field_diffs(prev, _passport("Вал"), "passport")}
    assert diffs["part_type"]["old"] == "не указано на чертеже"
    assert diffs["part_type"]["new"] == "Вал"


def test_route_cell_diff():
    prev = {"json": {"route": [{"code": "OP01", "equipment": "Токарный 16К20"}]}}
    curr = {"json": {"route": [{"code": "OP01", "equipment": "Токарный CTX"}]}}
    diffs = {d["field"]: d for d in compute_field_diffs(prev, curr, "technology")}
    assert "route[OP01].equipment" in diffs
    assert diffs["route[OP01].equipment"]["old"] == "Токарный 16К20"
    assert diffs["route[OP01].equipment"]["new"] == "Токарный CTX"


def test_route_operation_removed():
    prev = {
        "json": {
            "route": [
                {"code": "OP01", "equipment": "Токарный"},
                {"code": "OP02", "name": "Фрезерная", "equipment": "Фрезерный"},
            ]
        }
    }
    curr = {"json": {"route": [{"code": "OP01", "equipment": "Токарный"}]}}
    diffs = compute_field_diffs(prev, curr, "technology")
    removed = [d for d in diffs if d.get("kind") == "route_removed"]
    assert len(removed) == 1
    assert removed[0]["field"] == "route[OP02]"
    assert removed[0]["step"]["equipment"] == "Фрезерный"
    # для удалённой операции не должно быть поячейкового diff
    assert not any(d["field"].startswith("route[OP02].") for d in diffs)


def test_route_operation_added():
    prev = {"json": {"route": [{"code": "OP01", "equipment": "Токарный"}]}}
    curr = {
        "json": {
            "route": [
                {"code": "OP01", "equipment": "Токарный"},
                {"code": "OP02", "equipment": "Шлифовальный"},
            ]
        }
    }
    diffs = compute_field_diffs(prev, curr, "technology")
    added = [d for d in diffs if d.get("kind") == "route_added"]
    assert len(added) == 1
    assert added[0]["field"] == "route[OP02]"
    # добавленная операция помечается целиком, без поячейкового diff
    assert not any(d.get("field", "").startswith("route[OP02].") for d in diffs)


def test_unchanged_documents_have_no_diff():
    assert compute_field_diffs(_passport("Вал"), _passport("Вал"), "passport") == []


def test_stage_field_diffs_reads_history_pair():
    s = SimpleNamespace(
        llm_history={
            "passport": [
                {"kind": "artifact", "content": _passport("Тело вращения")},
                {"kind": "artifact", "content": _passport("Толкатель")},
            ]
        },
        passport=_passport("Толкатель"),
    )
    diffs = {d["field"]: d for d in stage_field_diffs(s, "passport")}
    assert diffs["part_type"]["old"] == "Тело вращения"
    assert diffs["part_type"]["new"] == "Толкатель"
