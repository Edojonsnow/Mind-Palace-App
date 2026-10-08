"""Add the lookup index used by AI job reconciliation.

Revision ID: 20261008_0011
Revises: 20261001_0010
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261008_0011"
down_revision: str | None = "20261001_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_background_jobs_ai_recovery",
        "background_jobs",
        ["job_type", "status", "not_before", "started_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_background_jobs_ai_recovery", table_name="background_jobs")
