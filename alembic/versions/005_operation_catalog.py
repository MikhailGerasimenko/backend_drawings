"""operation catalog + selected_operations on sessions

Revision ID: 005
Revises: 004
"""
from typing import Sequence, Union
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Дублируем пары по умолчанию для data-миграции
_DEFAULT_ROWS = [
    ("Ленточно-отрезная", "ARG330"),
    ("Ковка", "молот, печь"),
    ("Отжиг", "печь"),
    ("Токарная черновая", "16К20"),
    ("Токарная черновая", "CTX510"),
    ("Токарная чистовая", "16К20"),
    ("Токарная чистовая", "CTX510"),
    ("Вертикально-фрезерная", "6Т12"),
    ("Долбёжная", "7А-420"),
    ("Фрезерная ЧПУ", "Mikron"),
    ("Слесарная", "вручную"),
    ("Сверлильная", "2С132"),
    ("Заточная", "3А64Д"),
    ("Плоскошлифовальная", "3Л722В"),
    ("Круглошлифовальная", "3М151"),
    ("Внутришлифовальная", "3К227"),
    ("Цементация", "ПН-32"),
    ("Защитное карбонитрирование", "СШ36.6/7"),
    ("Закалка", "печь СВС-60"),
    ("Закалка", "печь CHO"),
    ("Закалка", "печь ПКМ6.84/12.5"),
    ("Пескоструйная", "установка"),
    ("Азотирование", "печь США6,9/7И2"),
    ("Упрочняющее карбонитрирование", "печь СШ36.6/7"),
    ("Отпуск низкий", "печь НК6.6/5И4"),
    ("Термоулучшение", "печь"),
    ("Маркировка", "вручную"),
    ("Контроль размеров", "вручную"),
]


def upgrade() -> None:
    op.create_table(
        "operation_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("teams.id"), nullable=False),
        sa.Column("operation", sa.String(255), nullable=False),
        sa.Column("equipment", sa.String(255), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.UniqueConstraint("team_id", "operation", "equipment", name="uq_operation_catalog"),
    )
    op.create_index("ix_operation_catalog_team", "operation_catalog", ["team_id"])

    op.add_column(
        "sessions",
        sa.Column(
            "selected_operations",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )

    conn = op.get_bind()
    teams = conn.execute(sa.text("SELECT id FROM teams")).fetchall()
    for (team_id,) in teams:
        n = conn.execute(
            sa.text("SELECT COUNT(*) FROM operation_catalog WHERE team_id = :tid"),
            {"tid": team_id},
        ).scalar()
        if n and int(n) > 0:
            continue
        for i, (operation, equipment) in enumerate(_DEFAULT_ROWS):
            conn.execute(
                sa.text(
                    """
                    INSERT INTO operation_catalog
                    (id, team_id, operation, equipment, sort_order, created_at)
                    VALUES (:id, :team_id, :operation, :equipment, :sort_order, NOW())
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "team_id": team_id,
                    "operation": operation,
                    "equipment": equipment,
                    "sort_order": i,
                },
            )


def downgrade() -> None:
    op.drop_column("sessions", "selected_operations")
    op.drop_index("ix_operation_catalog_team", table_name="operation_catalog")
    op.drop_table("operation_catalog")
