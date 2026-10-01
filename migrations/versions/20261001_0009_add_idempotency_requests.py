"""Add durable request idempotency.

Revision ID: 20261001_0009
Revises: 20261001_0008
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261001_0009"
down_revision: str | None = "20261001_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scope", sa.String(255), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("resource_kind", sa.String(32)),
        sa.Column("resource_id", sa.Uuid()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "scope", "key", name="uq_idempotency_action"),
    )
    op.create_index("ix_idempotency_requests_user_id", "idempotency_requests", ["user_id"])
    op.create_index("ix_idempotency_requests_expires_at", "idempotency_requests", ["expires_at"])


def downgrade() -> None:
    op.drop_table("idempotency_requests")
