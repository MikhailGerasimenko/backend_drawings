"""002-llm-conversation-memory: модуль истории переписки (FR-003/004/006/007/010)."""
import uuid

from sqlalchemy import select

from app.models import Team, User, WorkSession
from app.services.llm_history import (
    append_turn,
    build_messages,
    reset_stage,
    seed_if_empty,
    truncate_history,
)


def _make_session() -> WorkSession:
    return WorkSession(llm_history={})


def test_first_generation_without_history_fr004():
    """FR-004: первая генерация — только system + initial-вход."""
    s = _make_session()
    messages = build_messages(
        "passport",
        s,
        system_prompt="SYS",
        initial_user_content="DRAWING",
    )
    assert messages == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "DRAWING"},
    ]


def test_roles_order_accumulation_fr003_fr006():
    """FR-003/FR-006: накопление и порядок system→user→assistant/user*."""
    s = _make_session()
    append_turn(s, "passport", "assistant", "artifact", {"v": 1})
    append_turn(s, "passport", "user", "remark", "замечание 1")
    append_turn(s, "passport", "assistant", "artifact", {"v": 2})
    append_turn(s, "passport", "user", "remark", "замечание 2")

    messages = build_messages(
        "passport", s, system_prompt="SYS", initial_user_content="DRAWING"
    )
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user", "assistant", "user"]
    assert '{"v": 1}' in messages[2]["content"]
    assert "замечание 1" in messages[3]["content"]
    assert '{"v": 2}' in messages[4]["content"]
    assert "замечание 2" in messages[5]["content"]


def test_history_isolated_per_stage():
    s = _make_session()
    append_turn(s, "passport", "assistant", "artifact", {"p": 1})
    append_turn(s, "technology", "assistant", "artifact", {"text": "t", "json": {}})
    assert len(s.llm_history["passport"]) == 1
    assert len(s.llm_history["technology"]) == 1
    reset_stage(s, "technology")
    assert s.llm_history["technology"] == []
    assert len(s.llm_history["passport"]) == 1


def test_seed_if_empty_r07():
    """R-07: in-flight сессия — текущий артефакт как первая версия."""
    s = _make_session()
    seed_if_empty(s, "passport", {"v": "existing"})
    turns = s.llm_history["passport"]
    assert len(turns) == 1
    assert turns[0]["kind"] == "artifact"
    # Повторное сидирование не дублирует
    seed_if_empty(s, "passport", {"v": "existing"})
    assert len(s.llm_history["passport"]) == 1
    # Пустой артефакт не сидируется
    s2 = _make_session()
    seed_if_empty(s2, "passport", None)
    assert not (s2.llm_history or {}).get("passport")


def test_build_messages_seeds_from_session_artifact_r07():
    """R-07 внутри build_messages: история пуста, но артефакт в сессии есть."""
    s = _make_session()
    s.passport = {"schema_version": "2.0", "designation": {"value": "X"}}
    messages = build_messages(
        "passport", s, system_prompt="SYS", initial_user_content="DRAWING"
    )
    assert [m["role"] for m in messages] == ["system", "user", "assistant"]
    assert "designation" in messages[2]["content"]


def test_truncate_keeps_remarks_and_last_artifact_fr010():
    """FR-010: усечение убирает старые версии, сохраняя замечания и последнюю."""
    turns = []
    for i in range(1, 5):
        turns.append({"role": "assistant", "kind": "artifact", "content": {"v": i, "pad": "x" * 200}})
        turns.append({"role": "user", "kind": "remark", "content": f"замечание {i}"})

    result = truncate_history(turns, budget=600)
    remarks = [t for t in result if t["kind"] == "remark"]
    artifacts = [t for t in result if t["kind"] == "artifact"]
    assert len(remarks) == 4  # все замечания сохранены
    assert artifacts, "последняя версия артефакта сохранена"
    assert artifacts[-1]["content"]["v"] == 4
    # Удалены именно самые старые версии
    versions = [a["content"]["v"] for a in artifacts]
    assert versions == sorted(versions)
    assert 1 not in versions


def test_truncate_within_budget_no_changes_fr010():
    turns = [
        {"role": "assistant", "kind": "artifact", "content": {"v": 1}},
        {"role": "user", "kind": "remark", "content": "ок"},
    ]
    assert truncate_history(turns, budget=10_000) == turns


def test_truncate_single_artifact_untouched_fr010():
    turns = [
        {"role": "assistant", "kind": "artifact", "content": {"v": 1, "pad": "x" * 500}},
        {"role": "user", "kind": "remark", "content": "ок"},
    ]
    assert truncate_history(turns, budget=10) == turns


def test_build_messages_applies_budget_t026():
    """T026: малый бюджет усекает старые версии в собранных messages."""
    s = _make_session()
    for i in range(1, 4):
        append_turn(s, "passport", "assistant", "artifact", {"v": i, "pad": "x" * 300})
        append_turn(s, "passport", "user", "remark", f"замечание {i}")

    messages = build_messages(
        "passport", s, system_prompt="SYS", initial_user_content="DRAWING", budget=400
    )
    text = " ".join(m["content"] for m in messages if isinstance(m["content"], str))
    assert '"v": 3' in text  # последняя версия сохранена
    assert "замечание 1" in text and "замечание 2" in text and "замечание 3" in text
    assert '"v": 1' not in text  # самая старая версия усечена


def test_history_restored_from_db_fr007_t027():
    """T027/FR-007: история переживает «перезагрузку» (новый DB-сеанс)."""
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        team = db.scalars(select(Team)).first()
        user = db.scalars(select(User)).first()
        assert team and user
        s = WorkSession(
            id=uuid.uuid4(),
            team_id=team.id,
            created_by=user.id,
            title="llm-history-restore-test",
            status="passport_review",
            events=[],
            llm_history={},
        )
        append_turn(s, "passport", "assistant", "artifact", {"v": 1})
        append_turn(s, "passport", "user", "remark", "первое замечание")
        append_turn(s, "passport", "assistant", "artifact", {"v": 2})
        db.add(s)
        db.commit()
        sid = s.id
    finally:
        db.close()

    # Имитация перезагрузки: новый DB-сеанс, чтение из PostgreSQL
    db2 = SessionLocal()
    try:
        restored = db2.get(WorkSession, sid)
        assert restored is not None
        messages = build_messages(
            "passport", restored, system_prompt="SYS", initial_user_content="DRAWING"
        )
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "user", "assistant"]
        assert "первое замечание" in messages[3]["content"]
        assert '{"v": 2}' in messages[4]["content"]
        db2.delete(restored)
        db2.commit()
    finally:
        db2.close()
