"""avito sync fields

Revision ID: 0003_avito_sync
Revises: 0002_our_listings
Create Date: 2026-09-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_avito_sync"
down_revision = "0002_our_listings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("our_listings", sa.Column("avito_item_id", sa.BigInteger(), nullable=True))
    op.add_column("our_listings", sa.Column("avito_status", sa.String(32), nullable=True))
    op.add_column("our_listings", sa.Column("avito_url", sa.Text(), nullable=True))
    op.add_column(
        "our_listings",
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_our_listings_avito_item_id", "our_listings", ["avito_item_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_our_listings_avito_item_id", "our_listings", type_="unique")
    op.drop_column("our_listings", "last_synced_at")
    op.drop_column("our_listings", "avito_url")
    op.drop_column("our_listings", "avito_status")
    op.drop_column("our_listings", "avito_item_id")
