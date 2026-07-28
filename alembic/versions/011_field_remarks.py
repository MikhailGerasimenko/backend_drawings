"""sessions.field_remarks (черновики точечных и общих замечаний)

Revision ID: 011
Revises: 010

specs/006-field-remarks-diff/data-model.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Черновики замечаний по этапам; diff читается из существующей llm_history
    op.add_column(
        "sessions",
        sa.Column(
            "field_remarks",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "field_remarks")
