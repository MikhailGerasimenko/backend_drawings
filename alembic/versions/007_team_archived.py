"""teams.archived — архивирование команд

Revision ID: 007
Revises: 006
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "teams",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("teams", "archived", server_default=None)


def downgrade() -> None:
    op.drop_column("teams", "archived")
