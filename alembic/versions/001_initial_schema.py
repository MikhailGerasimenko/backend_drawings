"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-24

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("login", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("salt", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id")),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_login", "users", ["login"], unique=True)

    op.create_table(
        "auth_sessions",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "team_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("drawing_sent_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("drawing_mime", sa.String(64)),
        sa.Column("drawing_b64", sa.Text()),
        sa.Column("drawing_preview_url", sa.Text()),
        sa.Column("passport", postgresql.JSONB()),
        sa.Column("technology_text", sa.Text()),
        sa.Column("technology_json", postgresql.JSONB()),
        sa.Column("events", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.create_index("ix_sessions_team_updated", "sessions", ["team_id", "updated_at"])

    op.create_table(
        "statistics_agg",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), primary_key=True),
        sa.Column("sessions_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remarks_passport_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("remarks_technology_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_duration_sec", sa.BigInteger(), nullable=False, server_default="0"),
    )

    op.create_table(
        "app_config",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("app_config")
    op.drop_table("statistics_agg")
    op.drop_index("ix_sessions_team_updated", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("team_members")
    op.drop_table("auth_sessions")
    op.drop_index("ix_users_login", table_name="users")
    op.drop_table("users")
    op.drop_table("teams")
