"""Дедуп app_config и восстановление PRIMARY KEY на key.

Revision ID: 016
Revises: 015

В проде таблица app_config оказалась без UNIQUE/PK на key → дубликаты строк,
StaleDataError (12 vs 24) и падение ON CONFLICT. Миграция:
1) оставляет одну строку на каждый key;
2) добавляет PRIMARY KEY (key), если его ещё нет.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM app_config AS a
        USING app_config AS b
        WHERE a.key = b.key
          AND a.ctid < b.ctid
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'app_config'::regclass
                  AND contype IN ('p', 'u')
                  AND pg_get_constraintdef(oid) ILIKE '%(key)%'
            ) THEN
                ALTER TABLE app_config ADD CONSTRAINT app_config_pkey PRIMARY KEY (key);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # PK оставляем: откат к состоянию без уникальности опасен для данных
    pass
