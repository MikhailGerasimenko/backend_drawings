"""llm conversation memory: sessions.llm_history

Revision ID: 009
Revises: 008

specs/002-llm-conversation-memory/data-model.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "llm_history",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("sessions", "llm_history", server_default=None)


def downgrade() -> None:
    op.drop_column("sessions", "llm_history")
