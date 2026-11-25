"""Persist new-user onboarding without interrupting existing accounts.

Revision ID: 20261121_0015
Revises: 20261023_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0015"
down_revision: str | None = "20261023_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("onboarding_step", sa.String(32), nullable=False, server_default="privacy"),
    )
    op.add_column(
        "user_settings",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE user_settings SET onboarding_completed_at = CURRENT_TIMESTAMP, "
        "onboarding_step = 'first_thought'"
    )


def downgrade() -> None:
    op.drop_column("user_settings", "onboarding_completed_at")
    op.drop_column("user_settings", "onboarding_step")
