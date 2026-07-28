"""Удаление таблиц прайса и витрин FinOps

Revision ID: 014
Revises: 013

specs/007-analytics-grafana-rebuild/data-model.md §2.
Стоимость берётся из ответа модели (llm_requests_log.cost), агрегаты —
в Grafana-представлениях (013). Журналы llm_requests_log и user_actions_log
НЕ трогаются (FR-024).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("session_finops_summary")
    op.drop_table("daily_finops_stat")
    op.drop_table("llm_tariffs")


def downgrade() -> None:
    # Восстановление структуры (без данных) на случай отката
    op.create_table(
        "llm_tariffs",
        sa.Column("model_name", sa.String(128), primary_key=True),
        sa.Column("input_token_price_per_1m", sa.Numeric(12, 6), nullable=False),
        sa.Column("output_token_price_per_1m", sa.Numeric(12, 6), nullable=False),
        sa.Column("cached_token_price_per_1m", sa.Numeric(12, 6), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_table(
        "daily_finops_stat",
        sa.Column("stat_date", sa.Date, primary_key=True),
        sa.Column("team_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("model_name", sa.String(128), primary_key=True, server_default=""),
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
    )
    op.create_table(
        "session_finops_summary",
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("sessions.id"), primary_key=True),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("teams.id"), index=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("session_date", sa.Date, index=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("remark_iterations", sa.Integer, server_default="0"),
        sa.Column("total_cost", sa.Numeric(12, 6), server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
