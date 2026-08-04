"""fix app_config missing primary key and deduplicate

Revision ID: 016
Revises: 015
"""
from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем дубли: оставляем одну запись на key
    op.execute(
        """
        DELETE FROM app_config
        WHERE ctid NOT IN (
            SELECT MIN(ctid) FROM app_config GROUP BY key
        );
        """
    )
    # Идемпотентно добавляем PK, если его нет
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'app_config'::regclass
                  AND contype = 'p'
            ) THEN
                ALTER TABLE app_config ADD PRIMARY KEY (key);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE app_config DROP CONSTRAINT IF EXISTS app_config_pkey;
        """
    )
