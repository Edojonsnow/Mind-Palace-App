"""Track AI quota reservation across worker retries.

Revision ID: 20261023_0014
Revises: 20261023_0013
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0014"
down_revision: str | None = "20261023_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "background_jobs",
        sa.Column(
            "quota_reserved",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("background_jobs", "quota_reserved")
