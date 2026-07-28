"""session feedback + sessions.completed_by

Revision ID: 010
Revises: 009

specs/005-session-rating-feedback/data-model.md
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("completed_by", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sessions_completed_by_users",
        "sessions",
        "users",
        ["completed_by"],
        ["id"],
    )
    op.create_table(
        "session_feedback",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("stars", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("stars >= 1 AND stars <= 5", name="ck_session_feedback_stars"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_session_feedback_session_id"),
    )
    op.create_index(
        "session_feedback_team_id_created_at_idx",
        "session_feedback",
        ["team_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("session_feedback_team_id_created_at_idx", table_name="session_feedback")
    op.drop_table("session_feedback")
    op.drop_constraint("fk_sessions_completed_by_users", "sessions", type_="foreignkey")
    op.drop_column("sessions", "completed_by")
