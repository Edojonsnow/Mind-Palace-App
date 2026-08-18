"""create users thoughts settings

Revision ID: 20260818_0001
Revises:
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("auth_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_auth_user_id", "users", ["auth_user_id"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "thoughts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("thought_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_title", sa.String(length=255), nullable=True),
        sa.Column("source_author", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("book_title", sa.String(length=255), nullable=True),
        sa.Column("book_author", sa.String(length=255), nullable=True),
        sa.Column("page_reference", sa.String(length=100), nullable=True),
        sa.Column("manual_tags", sa.JSON(), nullable=False),
        sa.Column("storage_scope", sa.String(length=32), nullable=False),
        sa.Column("use_with_ask_my_mind", sa.Boolean(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_thoughts_user_id", "thoughts", ["user_id"])
    op.create_index("ix_thoughts_user_id_deleted_at", "thoughts", ["user_id", "deleted_at"])
    op.create_index("ix_thoughts_user_id_created_at", "thoughts", ["user_id", "created_at"])
    op.create_index(
        "ix_thoughts_user_id_use_with_ask_my_mind",
        "thoughts",
        ["user_id", "use_with_ask_my_mind"],
    )

    op.create_table(
        "user_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("default_use_with_ask_my_mind", sa.Boolean(), nullable=False),
        sa.Column("store_chat_history", sa.Boolean(), nullable=False),
        sa.Column("mobile_offline_cache_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
    op.drop_index("ix_thoughts_user_id_use_with_ask_my_mind", table_name="thoughts")
    op.drop_index("ix_thoughts_user_id_created_at", table_name="thoughts")
    op.drop_index("ix_thoughts_user_id_deleted_at", table_name="thoughts")
    op.drop_index("ix_thoughts_user_id", table_name="thoughts")
    op.drop_table("thoughts")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_auth_user_id", table_name="users")
    op.drop_table("users")

