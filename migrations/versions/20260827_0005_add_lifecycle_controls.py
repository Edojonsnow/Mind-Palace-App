"""add recovery, export, and account deletion controls

Revision ID: 20260827_0005
Revises: 20260820_0004
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260827_0005"
down_revision: str | None = "20260820_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("thoughts", sa.Column("purge_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_thoughts_purge_at", "thoughts", ["purge_at"])
    op.execute(
        "UPDATE thoughts SET purge_at = deleted_at + INTERVAL '30 days' "
        "WHERE deleted_at IS NOT NULL"
    )

    op.create_table(
        "export_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_export_requests_user_id", "export_requests", ["user_id"])

    op.create_table(
        "account_deletion_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("purge_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(
        "ix_account_deletion_requests_user_id",
        "account_deletion_requests",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_deletion_requests_user_id", table_name="account_deletion_requests")
    op.drop_table("account_deletion_requests")
    op.drop_index("ix_export_requests_user_id", table_name="export_requests")
    op.drop_table("export_requests")
    op.drop_index("ix_thoughts_purge_at", table_name="thoughts")
    op.drop_column("thoughts", "purge_at")
