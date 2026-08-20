"""add AI processing tables and status

Revision ID: 20260820_0002
Revises: 20260818_0001
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20260820_0002"
down_revision: str | None = "20260818_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.add_column(
        "thoughts",
        sa.Column(
            "ai_processing_status",
            sa.String(length=32),
            nullable=False,
            server_default="not_requested",
        ),
    )
    op.create_index(
        "ix_thoughts_user_id_ai_processing_status",
        "thoughts",
        ["user_id", "ai_processing_status"],
    )

    op.create_table(
        "thought_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("thought_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["thought_id"], ["thoughts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thought_id", "chunk_index", name="uq_thought_chunks_thought_index"),
    )
    op.create_index("ix_thought_chunks_user_id", "thought_chunks", ["user_id"])
    op.create_index("ix_thought_chunks_thought_id", "thought_chunks", ["thought_id"])
    op.create_index(
        "ix_thought_chunks_user_id_thought_id",
        "thought_chunks",
        ["user_id", "thought_id"],
    )

    op.create_table(
        "thought_metadata",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("thought_id", sa.Uuid(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("themes", sa.JSON(), nullable=False),
        sa.Column("emotions", sa.JSON(), nullable=False),
        sa.Column("people", sa.JSON(), nullable=False),
        sa.Column("places", sa.JSON(), nullable=False),
        sa.Column("books", sa.JSON(), nullable=False),
        sa.Column("key_questions", sa.JSON(), nullable=False),
        sa.Column("action_items", sa.JSON(), nullable=False),
        sa.Column("deterministic_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["thought_id"], ["thoughts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thought_id", name="uq_thought_metadata_thought_id"),
    )
    op.create_index("ix_thought_metadata_user_id", "thought_metadata", ["user_id"])
    op.create_index("ix_thought_metadata_thought_id", "thought_metadata", ["thought_id"])

    op.create_table(
        "background_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("thought_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["thought_id"], ["thoughts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_background_jobs_user_id", "background_jobs", ["user_id"])
    op.create_index("ix_background_jobs_thought_id", "background_jobs", ["thought_id"])
    op.create_index(
        "ix_background_jobs_status_created_at",
        "background_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_status_created_at", table_name="background_jobs")
    op.drop_index("ix_background_jobs_thought_id", table_name="background_jobs")
    op.drop_index("ix_background_jobs_user_id", table_name="background_jobs")
    op.drop_table("background_jobs")

    op.drop_index("ix_thought_metadata_thought_id", table_name="thought_metadata")
    op.drop_index("ix_thought_metadata_user_id", table_name="thought_metadata")
    op.drop_table("thought_metadata")

    op.drop_index("ix_thought_chunks_user_id_thought_id", table_name="thought_chunks")
    op.drop_index("ix_thought_chunks_thought_id", table_name="thought_chunks")
    op.drop_index("ix_thought_chunks_user_id", table_name="thought_chunks")
    op.drop_table("thought_chunks")

    op.drop_index("ix_thoughts_user_id_ai_processing_status", table_name="thoughts")
    op.drop_column("thoughts", "ai_processing_status")
