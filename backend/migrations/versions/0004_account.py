"""our_listings.account

Revision ID: 0004_account
Revises: 0003_avito_sync
Create Date: 2026-10-01
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_account"
down_revision = "0003_avito_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("our_listings", sa.Column("account", sa.String(64), nullable=True))
    op.create_index("ix_our_listings_account", "our_listings", ["account"])


def downgrade() -> None:
    op.drop_index("ix_our_listings_account", table_name="our_listings")
    op.drop_column("our_listings", "account")
