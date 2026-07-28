"""placeholder — восстановление цепочки для БД с alembic_version=004

Revision ID: 004
Revises: 003
Create Date: 2026-05-24

Ранее в volume могла остаться ревизия 004 без файла в git.
Изменений схемы нет (no-op).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
