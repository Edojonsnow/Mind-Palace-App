"""Add durable AI processing deferral timestamp.

Revision ID: 20261001_0010
Revises: 20261001_0009
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261001_0010"
down_revision: str | None = "20261001_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("background_jobs", sa.Column("not_before", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("background_jobs", "not_before")
