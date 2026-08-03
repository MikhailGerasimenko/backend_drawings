"""Read-only представления продуктовых метрик для Grafana

Revision ID: 013
Revises: 012

specs/007-analytics-grafana-rebuild/data-model.md §4.
Grafana подключается нативным Postgres-датасорсом и читает эти VIEW.
GRANT SELECT выдаётся роли grafana_ro, если она существует (создаётся в ops).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Продуктовые действия для DAU/WAU (синхронно с app.services.user_audit.PRODUCT_ACTIONS)
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

_VIEWS = (
    "v_user_activity_daily",
    "v_sessions_metrics",
    "v_session_remarks",
    "v_llm_requests",
)


def _actions_sql() -> str:
    return ", ".join("'" + a + "'" for a in _PRODUCT_ACTIONS)


def upgrade() -> None:
    actions = _actions_sql()

    # FR-012/FR-013: активность для DAU/WAU — строка на (день, пользователь, команда)
    op.execute(
        f"""
        CREATE VIEW v_user_activity_daily AS
        SELECT DISTINCT
            date(timestamp) AS activity_date,
            user_id,
            team_id
        FROM user_actions_log
        WHERE status = 'success'
          AND action_type IN ({actions});
        """
    )

    # FR-006/7, FR-014/15, FR-018/19: сессии, время формирования, доля полей
    op.execute(
        """
        CREATE VIEW v_sessions_metrics AS
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
            ) AS session_share_pct
        FROM sessions s;
        """
    )

    # FR-016/FR-017: итерации замечаний по этапам на сессию
    op.execute(
        """
        CREATE VIEW v_session_remarks AS
        SELECT
            s.id AS session_id,
            s.team_id,
            s.created_by AS user_id,
            date(s.created_at) AS remark_date,
            count(*) FILTER (WHERE ual.action_type = 'remark_passport') AS remarks_passport,
            count(*) FILTER (WHERE ual.action_type = 'remark_blank_allowance') AS remarks_blank_allowance,
            count(*) FILTER (WHERE ual.action_type = 'remark_technology') AS remarks_technology
        FROM sessions s
        LEFT JOIN user_actions_log ual ON ual.session_id = s.id
        WHERE s.status <> 'deleted'
        GROUP BY s.id, s.team_id, s.created_by, date(s.created_at);
        """
    )

    # FR-020/FR-021/FR-022: запросы, токены, стоимость (из ответа модели)
    op.execute(
        """
        CREATE VIEW v_llm_requests AS
        SELECT
            r.id AS request_id,
            r.timestamp,
            r.session_id,
            r.user_id,
            s.team_id,
            r.model_name,
            r.prompt_tokens,
            r.completion_tokens,
            r.cached_tokens,
            (r.prompt_tokens + r.completion_tokens) AS total_tokens,
            r.cost
        FROM llm_requests_log r
        JOIN sessions s ON s.id = r.session_id;
        """
    )

    # GRANT SELECT роли Grafana, если она существует (создаётся в ops, не в миграции)
    views_grant = "\n".join(
        f"            EXECUTE 'GRANT SELECT ON {v} TO grafana_ro';" for v in _VIEWS
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'grafana_ro') THEN
{views_grant}
            ELSE
                RAISE NOTICE 'role grafana_ro not found; skip GRANT (create it in ops)';
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for v in reversed(_VIEWS):
        op.execute(f"DROP VIEW IF EXISTS {v};")
