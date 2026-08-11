"""Журнал действий пользователя (user_actions_log)."""
import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import UserActionLog

# Продуктовые действия для DAU/WAU (status=success)
PRODUCT_ACTIONS = frozenset(
    {
        "session_created",
        "session_deleted",
        "drawing_uploaded",
        "drawing_analyze_submitted",
        "remark_passport",
        "remark_blank_allowance",
        "remark_technology",
        "passport_approved",
        "technology_approved",
        "export_passport_pdf",
        "export_technology_pdf",
        "export_technology_xlsx",
        "export_technology_json",
        "session_retry",
        "operations_selected",
        "operations_skipped",
        "session_feedback_submitted",
    }
)

# Маппинг событий sessions.events → action_type аудита
EVENT_TO_ACTION = {
    "session_created": "session_created",
    "drawing_uploaded": "drawing_uploaded",
    "analysis_started": "drawing_analyze_submitted",
    "remark_passport": "remark_passport",
    "remark_blank_allowance": "remark_blank_allowance",
    "remark_technology": "remark_technology",
    "passport_approved": "passport_approved",
    "technology_approved": "technology_approved",
    "retry_requested": "session_retry",
    "session_deleted": "session_deleted",
    "operations_selected": "operations_selected",
    "operations_skipped": "operations_skipped",
    "session_feedback_submitted": "session_feedback_submitted",
    "session_feedback_updated": "session_feedback_updated",
}

REMARK_ACTIONS = frozenset(
    {"remark_passport", "remark_blank_allowance", "remark_technology"}
)


def log_action(
    db: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    action_type: str,
    status: str = "success",
    session_id: UUID | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    db.add(
        UserActionLog(
            id=uuid.uuid4(),
            user_id=user_id,
            team_id=team_id,
            session_id=session_id,
            action_type=action_type,
            status=status,
            meta=meta or {},
        )
    )


def log_from_event(
    db: Session,
    *,
    user_id: UUID,
    team_id: UUID,
    session_id: UUID,
    event_type: str,
    status: str = "success",
    meta: dict[str, Any] | None = None,
) -> None:
    action = EVENT_TO_ACTION.get(event_type)
    if not action:
        return
    st = "review_required" if action in REMARK_ACTIONS else status
    log_action(
        db,
        user_id=user_id,
        team_id=team_id,
        session_id=session_id,
        action_type=action,
        status=st,
        meta=meta,
    )


def is_product_action(action_type: str) -> bool:
    return action_type in PRODUCT_ACTIONS
