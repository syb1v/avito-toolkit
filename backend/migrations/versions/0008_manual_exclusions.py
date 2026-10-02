"""listing region and manual exclusions

Revision ID: 0008_manual_exclusions
Revises: 0007_accounts
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_manual_exclusions"
down_revision = "0007_accounts"
branch_labels = None
depends_on = None

BACKFILL_REGION = """
UPDATE listings
SET region = lower(split_part(regexp_replace(url, '^https?://[^/]+/', ''), '/', 1))
WHERE url IS NOT NULL AND region IS NULL AND url LIKE '%avito%'
"""


def upgrade() -> None:
    op.add_column("listings", sa.Column("region", sa.String(64), nullable=True))
    op.create_index("ix_listings_region", "listings", ["region"])
    op.create_table(
        "listing_exclusions",
        sa.Column(
            "search_id",
            sa.Uuid(),
            sa.ForeignKey("searches.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "listing_id",
            sa.BigInteger(),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("reason", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(BACKFILL_REGION)


def downgrade() -> None:
    op.drop_table("listing_exclusions")
    op.drop_index("ix_listings_region", table_name="listings")
    op.drop_column("listings", "region")
