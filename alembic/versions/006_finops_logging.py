"""FinOps: llm_tariffs, user_actions_log, llm_requests_log, daily_finops_stat, session_finops_summary

Revision ID: 006
Revises: 005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_tariffs",
        sa.Column("model_name", sa.String(128), primary_key=True),
        sa.Column("input_token_price_per_1m", sa.Numeric(12, 6), nullable=False),
        sa.Column("output_token_price_per_1m", sa.Numeric(12, 6), nullable=False),
        sa.Column("cached_token_price_per_1m", sa.Numeric(12, 6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "user_actions_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("meta", postgresql.JSONB, server_default="{}"),
    )
    op.create_index("ix_user_actions_team_ts", "user_actions_log", ["team_id", "timestamp"])
    op.create_index("ix_user_actions_user_ts", "user_actions_log", ["user_id", "timestamp"])
    op.create_index("ix_user_actions_session", "user_actions_log", ["session_id"])

    op.create_table(
        "llm_requests_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, server_default="0"),
        sa.Column("cached_tokens", sa.Integer, server_default="0"),
        sa.Column("provider_response_cache_hit", sa.Boolean, server_default="false"),
        sa.Column("cost", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("payload_prompt", sa.Text, nullable=True),
        sa.Column("payload_response", sa.Text, nullable=True),
        sa.Column("meta", postgresql.JSONB, server_default="{}"),
    )
    op.create_index("ix_llm_requests_session_ts", "llm_requests_log", ["session_id", "timestamp"])
    op.create_index("ix_llm_requests_ts", "llm_requests_log", ["timestamp"])
    op.create_index("ix_llm_requests_model_ts", "llm_requests_log", ["model_name", "timestamp"])

    op.create_table(
        "daily_finops_stat",
        sa.Column("stat_date", sa.Date, nullable=False),
        # Без FK: team_id/user_id = 00000000… — организационный rollup
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("llm_calls", sa.Integer, server_default="0"),
        sa.Column("prompt_tokens_sum", sa.BigInteger, server_default="0"),
        sa.Column("completion_tokens_sum", sa.BigInteger, server_default="0"),
        sa.Column("cached_tokens_sum", sa.BigInteger, server_default="0"),
        sa.Column("cost_sum", sa.Numeric(14, 6), server_default="0"),
        sa.Column("sessions_distinct", sa.Integer, server_default="0"),
        sa.Column("remarks_passport_sum", sa.Integer, server_default="0"),
        sa.Column("remarks_technology_sum", sa.Integer, server_default="0"),
        sa.Column("sessions_completed", sa.Integer, server_default="0"),
        sa.Column("avg_session_duration_sec", sa.Numeric(12, 2), nullable=True),
        sa.Column("active_users", sa.Integer, server_default="0"),
        sa.PrimaryKeyConstraint("stat_date", "team_id", "user_id", "model_name"),
    )
    op.create_index("ix_daily_finops_date_team", "daily_finops_stat", ["stat_date", "team_id"])

    op.create_table(
        "session_finops_summary",
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sessions.id"), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("session_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("remark_iterations", sa.Integer, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 6), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_session_finops_team_date", "session_finops_summary", ["team_id", "session_date"])


def downgrade() -> None:
    op.drop_table("session_finops_summary")
    op.drop_table("daily_finops_stat")
    op.drop_table("llm_requests_log")
    op.drop_table("user_actions_log")
    op.drop_table("llm_tariffs")
