"""record AI enrichment provenance and source identity

Revision ID: 20260926_0007
Revises: 20260915_0006
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260926_0007"
down_revision: str | None = "20260915_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "thought_chunks",
        sa.Column("enrichment_schema_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "thought_chunks",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "thought_chunks",
        sa.Column("source_hash", sa.String(length=64), nullable=True),
    )

    op.add_column(
        "thought_metadata",
        sa.Column("enrichment_schema_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "thought_metadata",
        sa.Column("metadata_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "thought_metadata",
        sa.Column("source_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "thought_metadata",
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "background_jobs",
        sa.Column("enrichment_schema_version", sa.Integer(), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("metadata_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "background_jobs",
        sa.Column("source_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("background_jobs", "source_hash")
    op.drop_column("background_jobs", "metadata_model")
    op.drop_column("background_jobs", "embedding_model")
    op.drop_column("background_jobs", "enrichment_schema_version")

    op.drop_column("thought_metadata", "processed_at")
    op.drop_column("thought_metadata", "source_hash")
    op.drop_column("thought_metadata", "metadata_model")
    op.drop_column("thought_metadata", "enrichment_schema_version")

    op.drop_column("thought_chunks", "source_hash")
    op.drop_column("thought_chunks", "embedding_model")
    op.drop_column("thought_chunks", "enrichment_schema_version")
