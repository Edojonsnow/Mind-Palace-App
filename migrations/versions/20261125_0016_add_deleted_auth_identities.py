"""Prevent deleted identities from being recreated by unexpired access tokens.

Revision ID: 20261125_0016
Revises: 20261121_0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261125_0016"
down_revision: str | None = "20261121_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "deleted_auth_identities",
        sa.Column("auth_id_hash", sa.String(64), primary_key=True),
        sa.Column(
            "deleted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("deleted_auth_identities")
