"""Сессии: чертёж, анализ, паспорт, замечания, выгрузки."""
import base64
<<<<<<< HEAD
import re
=======
>>>>>>> gitlab/dev
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.core.exceptions import AppError
from app.models import SESSION_STATUS_DELETED, StatisticsAgg, Team, WorkSession, utcnow
from app.roles import can_modify_session
from app.schemas.sessions import (
    ActiveTimeRequest,
    ActiveTimeResponse,
    CreateSessionRequest,
    DrawingUploadResponse,
    RemarksSubmitRequest,
    SessionDetail,
    SessionFeedbackRequest,
    SessionFeedbackView,
    SessionSummary,
    StageFieldRemarks,
    TechnologyGenerateRequest,
)
from app.services.operation_catalog import catalog_entry_dict, list_catalog, resolve_selected_operations
from app.services.passport_normalize import normalize_passport, passport_session_title
from app.services.session_ai import enqueue_session_ai
from app.services.drawing import (
    can_replace_drawing,
    dxf_to_preview_url,
    read_and_validate_upload,
    resolve_preview_url,
    to_preview_url,
)
from app.services.blank_allowance_normalize import validate_blank_allowance_store
from app.services.document_diff import stage_field_diffs
from app.services.field_stats import snapshot_stage_acceptance
from app.services.field_remarks import (
    clear_stage_remarks,
    compose_remark_text,
    get_stage_remarks,
    has_field_remarks,
    set_stage_remarks,
)
from app.services.llm_history import append_turn, reset_stage, seed_if_empty
from app.services.technology_normalize import validate_technology_store
from app.services.pdf_passport import build_passport_pdf
from app.services.pdf_technology import build_technology_pdf
<<<<<<< HEAD
from app.services.xlsx_technology import build_technology_xlsx
=======
>>>>>>> gitlab/dev
from app.services.session_route import advance_after_operations_skipped, apply_operations_route
from app.services.session_feedback import (
    get_session_feedback,
    is_feedback_editable,
    submit_session_feedback,
    update_session_feedback,
)
from app.services.user_audit import log_action, log_from_event

router = APIRouter(tags=["sessions"])


class RemarkRequest(BaseModel):
    """FR-008: замечание без пустого текста (в т.ч. только пробелы)."""

    text: str

    @field_validator("text")
    @classmethod
    def text_not_blank(cls, v: str) -> str:
        t = v.strip()
        if not t:
            raise ValueError("Текст замечания обязателен")
        return t


def _push_event(
    db: Session,
    s: WorkSession,
    event_type: str,
    user_id: UUID,
    extra: dict | None = None,
) -> None:
    events = list(s.events or [])
    ev = {
        "type": event_type,
        "created_at": utcnow().isoformat(),
        "created_by": str(user_id),
    }
    if extra:
        ev.update(extra)
    events.append(ev)
    s.events = events[-50:]
    log_from_event(
        db,
        user_id=user_id,
        team_id=s.team_id,
        session_id=s.id,
        event_type=event_type,
        meta=extra,
    )


def _reset_blank_allowance(s: WorkSession) -> None:
    s.blank_allowance = None
    s.blank_allowance_approved = False
    s.blank_allowance_step_active = None


def _review_stage(status: str) -> str | None:
    """Активный этап согласования по статусу сессии (006)."""
    if status == "passport_review":
        return "passport"
    if status == "blank_allowance_review":
        return "blank_allowance"
    if status == "technology_review":
        return "technology"
    return None


def _session_detail(db: Session, s: WorkSession, *, viewer_user_id: UUID | None = None) -> SessionDetail:
    team = db.get(Team, s.team_id)
    ba = None
    if s.blank_allowance:
        try:
            ba = validate_blank_allowance_store(s.blank_allowance)
        except ValueError:
            ba = s.blank_allowance
    fb_row = get_session_feedback(db, s.id)
    show_prompt = (
        s.status == "completed"
        and s.completed_by is not None
        and viewer_user_id is not None
        and s.completed_by == viewer_user_id
        and not fb_row
    )
    fb_view = None
    if fb_row:
        fb_view = SessionFeedbackView(
            stars=fb_row.stars,
            comment=fb_row.comment,
            created_at=fb_row.created_at,
            editable=is_feedback_editable(fb_row, viewer_user_id),
        )
    # 006: diff текущей пары версий и черновики замечаний для активного этапа
    stage = _review_stage(s.status)
    field_diffs: dict = {}
    field_remarks_out: dict = {}
    has_remarks = False
    if stage:
        diffs = stage_field_diffs(s, stage)
        if diffs:
            field_diffs[stage] = diffs
        field_remarks_out[stage] = get_stage_remarks(s, stage)
        has_remarks = has_field_remarks(s, stage)
    return SessionDetail(
        id=s.id,
        title=s.title,
        status=s.status,
        created_at=s.created_at,
        updated_at=s.updated_at,
        passport=normalize_passport(s.passport) if s.passport else None,
        technology_text=s.technology_text,
        technology_json=s.technology_json,
        selected_operations=list(s.selected_operations or []),
        blank_allowance=ba,
        blank_allowance_approved=bool(s.blank_allowance_approved),
        blank_allowance_step_enabled=bool(team.blank_allowance_step_enabled) if team else False,
        drawing_preview_url=resolve_preview_url(
            s.drawing_preview_url, s.drawing_b64, s.drawing_mime
        ),
        drawing_mime=s.drawing_mime,
        drawing_sent_at=s.drawing_sent_at,
        events=(s.events or [])[-20:],
        show_feedback_prompt=show_prompt,
        feedback_submitted=fb_row is not None,
        session_feedback=fb_view,
        field_diffs=field_diffs,
        field_remarks=field_remarks_out,
        has_field_remarks=has_remarks,
    )


def _get_session_or_404(db: Session, session_id: UUID, team_id: UUID) -> WorkSession:
    s = db.get(WorkSession, session_id)
    if not s or s.team_id != team_id or s.status == SESSION_STATUS_DELETED:
        raise AppError("NOT_FOUND", "Сессия не найдена", 404)
    return s


def _assert_can_modify(s: WorkSession, user: CurrentUser) -> None:
    if s.status == SESSION_STATUS_DELETED:
        raise AppError("NOT_FOUND", "Сессия не найдена", 404)
    if not can_modify_session(user.user_role, user.user_id, s.created_by):
        raise AppError("FORBIDDEN", "Можно изменять только свои сессии", 403)


def _get_stats(db: Session, team_id: UUID) -> StatisticsAgg:
    st = db.get(StatisticsAgg, team_id)
    if not st:
        st = StatisticsAgg(team_id=team_id)
        db.add(st)
        db.flush()
    return st


@router.get("/sessions")
def list_sessions(db: DbSession, user: CurrentUser):
    rows = db.scalars(
        select(WorkSession)
        .where(WorkSession.team_id == user.team_id)
        .where(WorkSession.status != SESSION_STATUS_DELETED)
        .order_by(WorkSession.updated_at.desc())
    ).all()
    return {
        "sessions": [
            SessionSummary(
                id=s.id,
                title=s.title,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in rows
        ]
    }


@router.post("/sessions", response_model=SessionDetail)
def create_session(body: CreateSessionRequest, db: DbSession, user: CurrentUser):
    custom = (body.title or "").strip()
    if custom:
        title = custom
    else:
        n = db.scalar(
            select(func.count())
            .select_from(WorkSession)
            .where(WorkSession.team_id == user.team_id)
            .where(WorkSession.status != SESSION_STATUS_DELETED)
        ) or 0
        title = f"Сессия {n + 1}"
    s = WorkSession(
        team_id=user.team_id,
        created_by=user.user_id,
        title=title,
        status="draft_upload",
        events=[],
    )
    db.add(s)
    _get_stats(db, user.team_id).sessions_total += 1
    _push_event(db, s, "session_created", user.user_id)
    db.commit()
    db.refresh(s)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.get("/session", response_model=SessionDetail)
def get_session(
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(..., description="ID сессии"),
):
    s = _get_session_or_404(db, id, user.team_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/active-time", response_model=ActiveTimeResponse)
def add_active_time(
    body: ActiveTimeRequest,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(..., description="ID сессии"),
):
    """FR-008…FR-010: накопление чистого активного времени пользователя.

    Дельта прибавляется к user_active_seconds; работает и для завершённых
    сессий (финальный флуш), но не для удалённых.
    """
    s = db.get(WorkSession, id)
    if not s or s.team_id != user.team_id or s.status == SESSION_STATUS_DELETED:
        raise AppError("NOT_FOUND", "Сессия не найдена", 404)
    if not can_modify_session(user.user_role, user.user_id, s.created_by):
        raise AppError("FORBIDDEN", "Можно изменять только свои сессии", 403)
    s.user_active_seconds = (s.user_active_seconds or 0) + body.delta_seconds
    db.commit()
    return ActiveTimeResponse(user_active_seconds=s.user_active_seconds)


@router.put("/session/drawing", response_model=DrawingUploadResponse)
async def upload_drawing(
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
    file: UploadFile = File(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if not can_replace_drawing(s.status, s.drawing_sent_at):
        raise AppError(
            "INVALID_STATE",
            "Замена чертежа недоступна после отправки",
            409,
        )

    raw, mime = await read_and_validate_upload(file)
    s.drawing_mime = mime
    s.drawing_b64 = base64.b64encode(raw).decode("ascii")
    if mime == "application/dxf":
        preview_url, llm_context = await dxf_to_preview_url(raw)
        s.drawing_preview_url = preview_url
        # Кэш Markdown с первого convert — analyze не ходит в converter второй раз
        from app.services.dxf_converter_client import DXF_LLM_CONTEXT_KEY

        hist = dict(s.llm_history or {})
        if llm_context:
            hist[DXF_LLM_CONTEXT_KEY] = llm_context
        else:
            hist.pop(DXF_LLM_CONTEXT_KEY, None)
        s.llm_history = hist
    else:
        s.drawing_preview_url = to_preview_url(raw, mime)
    s.status = "ready_to_send"
    s.updated_at = datetime.now(timezone.utc)
    _push_event(db, s, "drawing_uploaded", user.user_id)
    db.commit()
    return DrawingUploadResponse(
        preview_url=s.drawing_preview_url,
        status=s.status,
    )


@router.post("/session/analyze", response_model=SessionDetail, status_code=202)
def start_analyze(
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if not s.drawing_preview_url:
        raise AppError("INVALID_STATE", "Сначала загрузите чертёж", 409)
    if s.drawing_sent_at:
        raise AppError("INVALID_STATE", "Анализ уже запущен", 409)

    s.drawing_sent_at = utcnow()
    s.status = "analyzing"
    s.updated_at = utcnow()
    _push_event(db, s, "analysis_started", user.user_id)
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/passport/remarks", response_model=SessionDetail, status_code=202)
def passport_remarks(
    body: RemarkRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "passport_review":
        raise AppError("INVALID_STATE", "Паспорт не на согласовании", 409)

    text = body.text
    st = _get_stats(db, user.team_id)
    st.remarks_passport_total += 1
    # Память переписки (FR-001): сидирование in-flight сессий (R-07) до очистки
    # артефакта, затем замечание как user-turn
    seed_if_empty(s, "passport", s.passport)
    append_turn(s, "passport", "user", "remark", text)
    s.passport = None
    s.status = "analyzing"
    s.updated_at = utcnow()
    _push_event(db, s, "remark_passport", user.user_id, {"text": text})
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.get("/statistics")
def team_statistics(db: DbSession, user: CurrentUser):
    """Агрегаты команды для панели статистики (Phase 5 — минимальный MVP)."""
    st = _get_stats(db, user.team_id)
    total = st.sessions_total or 0
    return {
        "sessions_total": total,
        "remarks_passport_total": st.remarks_passport_total,
        "remarks_technology_total": st.remarks_technology_total,
        "total_duration_sec": st.total_duration_sec,
        "avg_duration_sec": st.total_duration_sec / total if total else 0,
    }


@router.post("/session/technology/remarks", response_model=SessionDetail, status_code=202)
def technology_remarks(
    body: RemarkRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "technology_review":
        raise AppError("INVALID_STATE", "Технология не на согласовании", 409)

    text = body.text
    st = _get_stats(db, user.team_id)
    st.remarks_technology_total += 1
    # Память переписки (FR-002): сидирование R-07 + замечание до очистки артефакта
    if s.technology_text or s.technology_json:
        seed_if_empty(
            s, "technology", {"text": s.technology_text, "json": s.technology_json}
        )
    append_turn(s, "technology", "user", "remark", text)
    s.technology_text = None
    s.technology_json = None
    s.status = "generating_technology"
    s.updated_at = utcnow()
    _push_event(db, s, "remark_technology", user.user_id, {"text": text})
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/blank-allowance/remarks", response_model=SessionDetail, status_code=202)
def blank_allowance_remarks(
    body: RemarkRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "blank_allowance_review":
        raise AppError("INVALID_STATE", "Расчёт припусков не на согласовании", 409)

    text = body.text
    st = _get_stats(db, user.team_id)
    st.remarks_technology_total += 1
    # Память переписки (FR-008): сидирование R-07 + замечание до очистки расчёта
    seed_if_empty(s, "blank_allowance", s.blank_allowance)
    append_turn(s, "blank_allowance", "user", "remark", text)
    s.blank_allowance = None
    s.blank_allowance_approved = False
    s.status = "generating_blank_allowance"
    s.updated_at = utcnow()
    _push_event(db, s, "remark_blank_allowance", user.user_id, {"text": text})
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


def _apply_stage_remark(
    db: Session,
    s: WorkSession,
    stage: str,
    text: str,
    user_id: UUID,
    payload: dict,
) -> None:
    """Единый поток замечания этапа: история + сброс артефакта + статус + счётчик (006)."""
    st = _get_stats(db, s.team_id)
    if stage == "passport":
        st.remarks_passport_total += 1
        seed_if_empty(s, "passport", s.passport)
        append_turn(s, "passport", "user", "remark", text)
        s.passport = None
        s.status = "analyzing"
        event_type = "remark_passport"
    elif stage == "blank_allowance":
        st.remarks_technology_total += 1
        seed_if_empty(s, "blank_allowance", s.blank_allowance)
        append_turn(s, "blank_allowance", "user", "remark", text)
        s.blank_allowance = None
        s.blank_allowance_approved = False
        s.status = "generating_blank_allowance"
        event_type = "remark_blank_allowance"
    else:  # technology
        st.remarks_technology_total += 1
        if s.technology_text or s.technology_json:
            seed_if_empty(
                s, "technology", {"text": s.technology_text, "json": s.technology_json}
            )
        append_turn(s, "technology", "user", "remark", text)
        s.technology_text = None
        s.technology_json = None
        s.status = "generating_technology"
        event_type = "remark_technology"
    s.updated_at = utcnow()
    _push_event(db, s, event_type, user_id, payload)


@router.put("/session/field-remarks", response_model=SessionDetail)
def put_field_remarks(
    body: StageFieldRemarks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """Autosave черновиков точечных замечаний и общего текста активного этапа (006)."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    stage = _review_stage(s.status)
    if not stage:
        raise AppError("INVALID_STATE", "Этап не на согласовании", 409)
    applied = [r.model_dump() for r in body.applied]
    set_stage_remarks(s, stage, applied, body.general_draft)
    s.updated_at = utcnow()
    db.commit()
    db.refresh(s)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/remarks/submit", response_model=SessionDetail, status_code=202)
def submit_remarks(
    body: RemarksSubmitRequest,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """Отправка пакета замечаний (точечные + общий текст) → перегенерация (006)."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    stage = _review_stage(s.status)
    if not stage:
        raise AppError("INVALID_STATE", "Этап не на согласовании", 409)

    field_remarks = [r.model_dump() for r in body.field_remarks]
    general_text = (body.general_text or "").strip() or None
    if not field_remarks and not general_text:
        raise AppError("VALIDATION_ERROR", "Нет ни одного замечания для отправки", 400)

    text = compose_remark_text(field_remarks, general_text)
    payload = {
        "field_remarks": field_remarks,
        "general_text": general_text,
        "text": text,
    }
    # F1: черновики НЕ очищаем здесь — очистка в ai.py после успешной генерации
    _apply_stage_remark(db, s, stage, text, user.user_id, payload)
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/blank-allowance/approve", response_model=SessionDetail, status_code=202)
def blank_allowance_approve(
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """FR-051: после согласования расчёта — автозапуск генерации технологии."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "blank_allowance_review":
        raise AppError("INVALID_STATE", "Расчёт припусков не на согласовании", 409)
    if not s.blank_allowance:
        raise AppError("INVALID_STATE", "Расчёт ещё не сформирован", 409)
    validate_blank_allowance_store(s.blank_allowance)

    # FR-018/FR-019: снимок доли полей, принятых без замечаний (до смены статуса)
    snapshot_stage_acceptance(s, "blank_allowance")
    s.blank_allowance_approved = True
    s.status = "generating_technology"
    s.updated_at = utcnow()
    _push_event(db, s, "blank_allowance_approved", user.user_id)
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/technology/approve", response_model=SessionDetail)
def technology_approve(
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "technology_review":
        raise AppError("INVALID_STATE", "Технология не на согласовании", 409)
    if not s.technology_text and not s.technology_json:
        raise AppError("INVALID_STATE", "Технология ещё не сформирована", 409)

    if s.technology_json:
        validate_technology_store(s.technology_json)
    # FR-018/FR-019: снимок доли полей технологии, принятых без замечаний
    snapshot_stage_acceptance(s, "technology")
    dur = int((utcnow() - s.created_at).total_seconds())
    st = _get_stats(db, user.team_id)
    st.total_duration_sec += max(0, dur)
    s.status = "completed"
    s.completed_at = utcnow()
    s.completed_by = user.user_id
    s.updated_at = utcnow()
    _push_event(db, s, "technology_approved", user.user_id)
    db.commit()
    db.refresh(s)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/feedback", response_model=SessionDetail)
def submit_feedback(
    body: SessionFeedbackRequest,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """Оценка сессии после согласования технологии (005)."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    submit_session_feedback(db, s, user, body.stars, body.comment)
    _push_event(db, s, "session_feedback_submitted", user.user_id, {"stars": body.stars})
    db.commit()
    db.refresh(s)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.put("/session/feedback", response_model=SessionDetail)
def update_feedback(
    body: SessionFeedbackRequest,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """Изменение оценки в течение 24 ч после первой отправки."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    update_session_feedback(db, s, user, body.stars, body.comment)
    _push_event(db, s, "session_feedback_updated", user.user_id, {"stars": body.stars})
    db.commit()
    db.refresh(s)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/retry", response_model=SessionDetail, status_code=202)
def retry_session(
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """Повтор после ошибки: паспорт или технология (паспорт при сбое технологии сохраняется)."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)

    if s.status == "blank_allowance_failed" and s.passport:
        s.status = "generating_blank_allowance"
    elif s.status in ("technology_failed", "failed") and s.passport:
        s.technology_text = None
        s.technology_json = None
        s.status = "generating_technology"
    elif s.status in ("passport_failed",) or (s.status == "failed" and not s.passport):
        s.passport = None
        s.technology_text = None
        s.technology_json = None
        s.status = "analyzing"
    else:
        raise AppError(
            "INVALID_STATE",
            "Повтор доступен только после ошибки генерации",
            409,
        )

    s.updated_at = utcnow()
    _push_event(db, s, "retry_requested", user.user_id)
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/passport/approve", response_model=SessionDetail, status_code=202)
def passport_approve(
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "passport_review":
        raise AppError("INVALID_STATE", "Паспорт не на согласовании", 409)

    new_title = passport_session_title(normalize_passport(s.passport))
    if new_title:
        s.title = new_title

    # FR-018/FR-019: снимок доли полей паспорта, принятых без замечаний (до сброса)
    snapshot_stage_acceptance(s, "passport")
    # После согласования — выбор операций из справочника, затем расчёт припусков или технология
    s.status = "operations_selection"
    s.selected_operations = []
    s.technology_text = None
    s.technology_json = None
    _reset_blank_allowance(s)
    s.updated_at = utcnow()
    _push_event(db, s, "passport_approved", user.user_id)
    db.commit()
    db.refresh(s)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.get("/operation-catalog")
def get_team_operation_catalog(db: DbSession, user: CurrentUser):
    """Справочник операций команды для выбора перед генерацией технологии."""
    rows = list_catalog(db, user.team_id)
    return {"entries": [catalog_entry_dict(r) for r in rows]}


def _advance_after_operations_selected(
    db: Session,
    background_tasks: BackgroundTasks,
    s: WorkSession,
    selected: list[dict],
    user_id: UUID,
    *,
    event_type: str = "operations_selected",
) -> SessionDetail:
    """Общий переход после ручного или автоматического выбора маршрута."""
    apply_operations_route(db, s, selected)
    _push_event(db, s, event_type, user_id, {"count": len(selected)})
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user_id)
    return _session_detail(db, s, viewer_user_id=user_id)


@router.post("/session/technology/generate", response_model=SessionDetail, status_code=202)
def generate_technology_session(
    background_tasks: BackgroundTasks,
    body: TechnologyGenerateRequest,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "operations_selection":
        raise AppError("INVALID_STATE", "Сначала согласуйте паспорт и выберите операции", 409)
    if not s.passport:
        raise AppError("INVALID_STATE", "Нет паспорта детали", 409)
    try:
        selected = resolve_selected_operations(db, user.team_id, body.catalog_ids)
    except ValueError as e:
        raise AppError("VALIDATION_ERROR", str(e), 400) from e
    return _advance_after_operations_selected(
        db, background_tasks, s, selected, user.user_id
    )


@router.post("/session/technology/auto-select", response_model=SessionDetail, status_code=202)
def auto_select_operations_session(
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """Пропуск ручного выбора — сразу расчёт припусков или технология (маршрут в system prompt)."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status != "operations_selection":
        raise AppError("INVALID_STATE", "Сначала согласуйте паспорт", 409)
    if not s.passport:
        raise AppError("INVALID_STATE", "Нет паспорта детали", 409)
    if not list_catalog(db, user.team_id):
        raise AppError("VALIDATION_ERROR", "Справочник операций пуст", 400)
    advance_after_operations_skipped(db, s)
    _push_event(db, s, "operations_skipped", user.user_id)
    db.commit()
    db.refresh(s)
    enqueue_session_ai(background_tasks, s.id, user.user_id)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.post("/session/technology/reselect-operations", response_model=SessionDetail)
def technology_reselect_operations(
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    """Вернуться к выбору операций; расчёт припусков/технология на экране остаются для справки."""
    s = _get_session_or_404(db, id, user.team_id)
    _assert_can_modify(s, user)
    if s.status not in ("technology_review", "blank_allowance_review"):
        raise AppError(
            "INVALID_STATE",
            "Доступно на этапе согласования расчёта припусков или технологии",
            409,
        )
    if not s.selected_operations and not any(
        ev.get("type") == "operations_skipped" for ev in (s.events or [])
    ):
        raise AppError("INVALID_STATE", "Нет ранее выбранных операций", 409)
    # После согласования припусков сброс при возврате с этапа технологии (FR-049)
    if s.status == "technology_review":
        _reset_blank_allowance(s)
    s.status = "operations_selection"
    s.updated_at = utcnow()
    _push_event(db, s, "operations_reselection", user.user_id)
    db.commit()
    db.refresh(s)
    return _session_detail(db, s, viewer_user_id=user.user_id)


@router.get("/session/exports/{export_type}")
def export_session(
    export_type: str,
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
):
    s = _get_session_or_404(db, id, user.team_id)
    if export_type == "passport_pdf":
        if not s.passport:
            raise AppError("INVALID_STATE", "Паспорт ещё не сформирован", 409)
        log_action(
            db,
            user_id=user.user_id,
            team_id=user.team_id,
            session_id=s.id,
            action_type="export_passport_pdf",
            meta={"export_format": "PDF"},
        )
        data_url = build_passport_pdf(s.title, s.passport)
        db.commit()
        return {
            "download_url": data_url,
            "file_name": f"passport_{id}.pdf",
        }
<<<<<<< HEAD
    if export_type in ("technology_json", "technology_pdf", "technology_xlsx"):
=======
    if export_type in ("technology_json", "technology_pdf"):
>>>>>>> gitlab/dev
        # FR-017: финальная выгрузка технологии — только после «Согласовано»
        if s.status != "completed":
            raise AppError(
                "INVALID_STATE",
                "Выгрузка технологии доступна после согласования",
                409,
            )
        if not s.technology_text and not s.technology_json:
            raise AppError("INVALID_STATE", "Технология ещё не сформирована", 409)
    if export_type == "technology_json":
        if not s.technology_json:
            raise AppError("INVALID_STATE", "Технология ещё не сформирована", 409)
        validate_technology_store(s.technology_json)
        log_action(
            db,
            user_id=user.user_id,
            team_id=user.team_id,
            session_id=s.id,
            action_type="export_technology_json",
            meta={"export_format": "JSON"},
        )
        db.commit()
        return s.technology_json
<<<<<<< HEAD
    if export_type == "technology_xlsx":
        log_action(
            db,
            user_id=user.user_id,
            team_id=user.team_id,
            session_id=s.id,
            action_type="export_technology_xlsx",
            meta={"export_format": "XLSX"},
        )
        data_url = build_technology_xlsx(
            s.title,
            s.technology_json,
            passport=s.passport,
            technology_text=s.technology_text,
        )
        designation = ""
        if isinstance(s.technology_json, dict):
            designation = (
                (s.technology_json.get("header") or {}).get("part_designation")
                or ""
            )
        safe_name = re.sub(r"[^\w.\-]+", "_", designation or str(id), flags=re.UNICODE)
        db.commit()
        return {
            "download_url": data_url,
            "file_name": f"{safe_name or f'technology_{id}'}.xlsx",
        }
=======
>>>>>>> gitlab/dev
    if export_type == "technology_pdf":
        log_action(
            db,
            user_id=user.user_id,
            team_id=user.team_id,
            session_id=s.id,
            action_type="export_technology_pdf",
            meta={"export_format": "PDF"},
        )
        data_url = build_technology_pdf(s.title, s.technology_text or "")
        db.commit()
        return {
            "download_url": data_url,
            "file_name": f"technology_{id}.pdf",
        }
    raise AppError("VALIDATION_ERROR", "Неизвестный тип выгрузки", 400)


@router.delete("/session", status_code=200)
def delete_session(
    db: DbSession,
    user: CurrentUser,
    id: UUID = Query(...),
    confirm: bool = Query(False),
):
    """Мягкое удаление (FR-027): status=deleted, строка и логи в БД, в списке UI скрыта."""
    if not confirm:
        raise AppError("VALIDATION_ERROR", "Требуется confirm=true", 400)
    s = db.get(WorkSession, id)
    if not s or s.team_id != user.team_id:
        raise AppError("NOT_FOUND", "Сессия не найдена", 404)
    if s.status == SESSION_STATUS_DELETED:
        return {"ok": True}
    _assert_can_modify(s, user)
    s.status = SESSION_STATUS_DELETED
    s.updated_at = utcnow()
    _push_event(db, s, "session_deleted", user.user_id)
    db.commit()
    return {"ok": True}
