"""blank_allowance: teams flag, sessions JSON, prompt kind

Revision ID: 008
Revises: 007
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column(
            "blank_allowance_step_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("teams", "blank_allowance_step_enabled", server_default=None)

    op.add_column("sessions", sa.Column("blank_allowance", JSONB(), nullable=True))
    op.add_column(
        "sessions",
        sa.Column(
            "blank_allowance_approved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.alter_column("sessions", "blank_allowance_approved", server_default=None)
    # Снимок флага шага на момент «Сформировать» (админ может выключить шаг позже)
    op.add_column(
        "sessions",
        sa.Column("blank_allowance_step_active", sa.Boolean(), nullable=True),
    )

    op.alter_column(
        "prompt_versions",
        "kind",
        existing_type=sa.String(length=16),
        type_=sa.String(length=32),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "prompt_versions",
        "kind",
        existing_type=sa.String(length=32),
        type_=sa.String(length=16),
        existing_nullable=False,
    )
    op.drop_column("sessions", "blank_allowance_approved")
    op.drop_column("sessions", "blank_allowance")
    op.drop_column("teams", "blank_allowance_step_enabled")
