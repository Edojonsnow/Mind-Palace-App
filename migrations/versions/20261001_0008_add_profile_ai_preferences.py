"""Add private profile and opt-in AI preferences.

Revision ID: 20261001_0008
Revises: 20260926_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261001_0008"
down_revision: str | None = "20260926_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(2048), nullable=True))
    op.create_table(
        "ai_preferences",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("use_profile_context", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("writing_style", sa.String(32), nullable=False, server_default="natural"),
        sa.Column("response_detail", sa.String(32), nullable=False, server_default="balanced"),
        sa.Column("personal_goals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("interests", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("ai_preferences")
    op.drop_column("users", "avatar_url")
