"""Add user-owned collections and thought memberships.

Revision ID: 20261023_0013
Revises: 20261008_0012
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0013"
down_revision: str | None = "20261008_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_collections_user_normalized_name",
        ),
    )
    op.create_index("ix_collections_user_id", "collections", ["user_id"])
    op.create_index(
        "ix_collections_user_id_last_accessed_at",
        "collections",
        ["user_id", "last_accessed_at"],
    )

    op.create_table(
        "collection_thoughts",
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("thought_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thought_id"], ["thoughts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("collection_id", "thought_id"),
    )
    op.create_index("ix_collection_thoughts_thought_id", "collection_thoughts", ["thought_id"])


def downgrade() -> None:
    op.drop_index("ix_collection_thoughts_thought_id", table_name="collection_thoughts")
    op.drop_table("collection_thoughts")
    op.drop_index("ix_collections_user_id_last_accessed_at", table_name="collections")
    op.drop_index("ix_collections_user_id", table_name="collections")
    op.drop_table("collections")
