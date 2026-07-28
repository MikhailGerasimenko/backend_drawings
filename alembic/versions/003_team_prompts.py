"""team prompt versions + model connection keys

Revision ID: 003
Revises: 002
Create Date: 2026-05-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
    )
    op.create_index(
        "ix_prompt_versions_team_kind",
        "prompt_versions",
        ["team_id", "kind", "version_no"],
    )

    # Миграция старых ключей Openrouter → отдельные настройки паспорт/технология
    op.execute(
        """
        INSERT INTO app_config (key, value)
        SELECT 'passportModelBaseUrl', value FROM app_config WHERE key = 'openrouterBaseUrl'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO app_config (key, value)
        SELECT 'technologyModelBaseUrl', value FROM app_config WHERE key = 'openrouterBaseUrl'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO app_config (key, value)
        SELECT 'passportModelKey', value FROM app_config WHERE key = 'openrouterApiKey'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO app_config (key, value)
        SELECT 'technologyModelKey', value FROM app_config WHERE key = 'openrouterApiKey'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO app_config (key, value)
        SELECT 'passportModelModel', value FROM app_config WHERE key = 'aiModel'
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO app_config (key, value)
        SELECT 'technologyModelModel', value FROM app_config WHERE key = 'aiModel'
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_prompt_versions_team_kind", table_name="prompt_versions")
    op.drop_table("prompt_versions")
