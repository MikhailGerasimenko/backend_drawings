"""Оценка завершённой сессии — specs/005-session-rating-feedback."""
import uuid
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import CurrentUser
from app.core.exceptions import AppError
from app.models import SessionFeedback, WorkSession, utcnow

COMMENT_MAX_LEN = 2000
FEEDBACK_EDIT_WINDOW = timedelta(hours=24)


def validate_feedback(stars: int, comment: str | None) -> str | None:
    """Валидация оценки; возвращает нормализованный comment или None."""
    if stars < 1 or stars > 5:
        raise AppError("VALIDATION_ERROR", "Оценка должна быть от 1 до 5", 400)
    text = (comment or "").strip()
    if len(text) > COMMENT_MAX_LEN:
        raise AppError(
            "VALIDATION_ERROR",
            f"Комментарий не длиннее {COMMENT_MAX_LEN} символов",
            400,
        )
    if stars <= 4 and not text:
        raise AppError(
            "VALIDATION_ERROR",
            "При оценке 4 и ниже комментарий обязателен",
            400,
        )
    return text or None


def get_session_feedback(db: Session, session_id: UUID) -> SessionFeedback | None:
    return db.scalar(
        select(SessionFeedback).where(SessionFeedback.session_id == session_id)
    )


def feedback_exists(db: Session, session_id: UUID) -> bool:
    return get_session_feedback(db, session_id) is not None


def is_feedback_editable(row: SessionFeedback, user_id: UUID | None) -> bool:
    """Редактирование доступно автору оценки в течение 24 ч с момента отправки."""
    if not user_id or row.user_id != user_id:
        return False
    return utcnow() < row.created_at + FEEDBACK_EDIT_WINDOW


def _assert_feedback_author(session: WorkSession, user: CurrentUser) -> None:
    if not session.completed_by or session.completed_by != user.user_id:
        raise AppError("FORBIDDEN", "Оценку может оставить только завершивший сессию", 403)


def submit_session_feedback(
    db: Session,
    session: WorkSession,
    user: CurrentUser,
    stars: int,
    comment: str | None,
) -> SessionFeedback:
    if session.status != "completed":
        raise AppError("INVALID_STATE", "Оценка доступна только для завершённой сессии", 409)
    _assert_feedback_author(session, user)

    if get_session_feedback(db, session.id):
        raise AppError("CONFLICT", "Оценка по этой сессии уже отправлена", 409)

    normalized = validate_feedback(stars, comment)
    row = SessionFeedback(
        id=uuid.uuid4(),
        session_id=session.id,
        team_id=session.team_id,
        user_id=user.user_id,
        stars=stars,
        comment=normalized,
        created_at=utcnow(),
    )
    db.add(row)
    return row


def update_session_feedback(
    db: Session,
    session: WorkSession,
    user: CurrentUser,
    stars: int,
    comment: str | None,
) -> SessionFeedback:
    if session.status != "completed":
        raise AppError("INVALID_STATE", "Оценка доступна только для завершённой сессии", 409)
    _assert_feedback_author(session, user)

    row = get_session_feedback(db, session.id)
    if not row:
        raise AppError("NOT_FOUND", "Оценка по этой сессии ещё не отправлена", 404)
    if not is_feedback_editable(row, user.user_id):
        raise AppError(
            "FORBIDDEN",
            "Изменить оценку можно только в течение 24 часов после отправки",
            403,
        )

    normalized = validate_feedback(stars, comment)
    row.stars = stars
    row.comment = normalized
    return row
