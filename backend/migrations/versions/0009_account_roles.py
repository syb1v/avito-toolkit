"""account roles: searcher / seller

Revision ID: 0009_account_roles
Revises: 0008_manual_exclusions
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_account_roles"
down_revision = "0008_manual_exclusions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "avito_accounts",
        sa.Column("role", sa.String(20), nullable=False, server_default="searcher"),
    )


def downgrade() -> None:
    op.drop_column("avito_accounts", "role")
