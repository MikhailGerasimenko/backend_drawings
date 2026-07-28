"""sessions: agent_seconds, user_active_seconds, field_acceptance (метрики)

Revision ID: 012
Revises: 011

specs/007-analytics-grafana-rebuild/data-model.md §1
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Серверное время агентских операций по сессии (FR-007/FR-011)
    op.add_column(
        "sessions",
        sa.Column(
            "agent_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # Чистое активное время пользователя (FR-008…FR-010, FR-025)
    op.add_column(
        "sessions",
        sa.Column(
            "user_active_seconds",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    # Снимок доли неизменных полей по этапам на момент согласования (FR-018/FR-019)
    op.add_column(
        "sessions",
        sa.Column(
            "field_acceptance",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "field_acceptance")
    op.drop_column("sessions", "user_active_seconds")
    op.drop_column("sessions", "agent_seconds")
