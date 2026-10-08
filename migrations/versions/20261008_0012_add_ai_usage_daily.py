"""Add durable daily AI usage accounting.

Revision ID: 20261008_0012
Revises: 20261008_0011
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_0012"
down_revision: str | None = "20261008_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_daily",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("usage_date", sa.Date(), primary_key=True),
        sa.Column("units_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ask_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("search_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organization_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_daily")
