"""account sticky proxy

Revision ID: 0011_account_proxy
Revises: 0010_orphan_alerts
Create Date: 2026-10-03
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_account_proxy"
down_revision = "0010_orphan_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("avito_accounts", sa.Column("proxy_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("avito_accounts", "proxy_url")
