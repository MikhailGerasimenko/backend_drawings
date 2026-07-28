"""Доп. представления для Grafana: события активности, оценки; +title/updated_at в сессиях

Revision ID: 015
Revises: 014

specs/007-analytics-grafana-rebuild — расширение дашборда продуктовых метрик:
- v_user_activity_events: продуктовые события с временем (для 5-минутных бакетов);
- v_session_feedback: оценки и комментарии завершённых сессий;
- v_sessions_metrics: добавлены title, updated_at, updated_date (CREATE OR REPLACE).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Синхронно с app.services.user_audit.PRODUCT_ACTIONS / миграцией 013
_PRODUCT_ACTIONS = (
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
    "export_technology_json",
    "session_retry",
    "operations_selected",
    "operations_skipped",
    "session_feedback_submitted",
)

_NEW_VIEWS = ("v_user_activity_events", "v_session_feedback")

# Базовое определение v_sessions_metrics из миграции 013 (порядок колонок сохраняется)
_SESSIONS_METRICS_BASE = """
    SELECT
        s.id AS session_id,
        s.team_id,
        s.created_by AS user_id,
        s.created_at,
        date(s.created_at) AS created_date,
        s.completed_at,
        date(s.completed_at) AS completed_date,
        s.status,
        (s.status = 'deleted') AS is_deleted,
        (s.status = 'completed') AS is_completed,
        s.agent_seconds,
        s.user_active_seconds,
        (s.agent_seconds + s.user_active_seconds) AS total_formation_seconds,
        (s.field_acceptance -> 'passport' ->> 'share_pct')::numeric AS passport_share_pct,
        (s.field_acceptance -> 'blank_allowance' ->> 'share_pct')::numeric AS blank_allowance_share_pct,
        (s.field_acceptance -> 'technology' ->> 'share_pct')::numeric AS technology_share_pct,
        (
            SELECT avg(v) FROM (VALUES
                ((s.field_acceptance -> 'passport' ->> 'share_pct')::numeric),
                ((s.field_acceptance -> 'blank_allowance' ->> 'share_pct')::numeric),
                ((s.field_acceptance -> 'technology' ->> 'share_pct')::numeric)
            ) AS t(v) WHERE v IS NOT NULL
        ) AS session_share_pct{extra}
    FROM sessions s;
"""


def _actions_sql() -> str:
    return ", ".join("'" + a + "'" for a in _PRODUCT_ACTIONS)


def upgrade() -> None:
    actions = _actions_sql()

    # Продуктовые события с временем — для графика активности (5-мин бакеты)
    op.execute(
        f"""
        CREATE VIEW v_user_activity_events AS
        SELECT
            timestamp,
            user_id,
            team_id,
            action_type
        FROM user_actions_log
        WHERE status = 'success'
          AND action_type IN ({actions});
        """
    )

    # Оценки и комментарии завершённых сессий
    op.execute(
        """
        CREATE VIEW v_session_feedback AS
        SELECT
            f.id AS feedback_id,
            f.session_id,
            f.team_id,
            f.user_id,
            f.stars,
            f.comment,
            f.created_at,
            s.title AS session_title
        FROM session_feedback f
        JOIN sessions s ON s.id = f.session_id;
        """
    )

    # Добавляем title/updated_at/updated_date в конец v_sessions_metrics
    extra = (
        ",\n        s.title,\n        s.updated_at,\n        date(s.updated_at) AS updated_date"
    )
    op.execute(
        "CREATE OR REPLACE VIEW v_sessions_metrics AS"
        + _SESSIONS_METRICS_BASE.format(extra=extra)
    )

    # GRANT новым представлениям, если роль grafana_ro существует
    grants = "\n".join(
        f"            EXECUTE 'GRANT SELECT ON {v} TO grafana_ro';" for v in _NEW_VIEWS
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
{grants}
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_session_feedback;")
    op.execute("DROP VIEW IF EXISTS v_user_activity_events;")
    # CREATE OR REPLACE не умеет удалять колонки → пересоздаём представление
    op.execute("DROP VIEW IF EXISTS v_sessions_metrics;")
    op.execute("CREATE VIEW v_sessions_metrics AS" + _SESSIONS_METRICS_BASE.format(extra=""))
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
                EXECUTE 'GRANT SELECT ON v_sessions_metrics TO grafana_ro';
            END IF;
        END $$;
        """
    )
