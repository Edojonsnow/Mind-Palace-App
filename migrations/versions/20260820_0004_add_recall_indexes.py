"""add Recall query index

Revision ID: 20260820_0004
Revises: 20260820_0003
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260820_0004"
down_revision: str | None = "20260820_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_thoughts_user_deleted_archived_created_at",
        "thoughts",
        ["user_id", "deleted_at", "is_archived", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_thoughts_user_deleted_archived_created_at",
        table_name="thoughts",
    )
