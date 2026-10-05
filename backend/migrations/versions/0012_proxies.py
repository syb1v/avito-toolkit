"""UI-managed proxies

Revision ID: 0012_proxies
Revises: 0011_account_proxy
Create Date: 2026-10-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_proxies"
down_revision = "0011_account_proxy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proxies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("note", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("proxies")
