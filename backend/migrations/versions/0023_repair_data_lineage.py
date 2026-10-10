"""Repair ownership and remove provable orphan market data.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # There is one searcher in the current installation. Only use this
    # deterministic rule when exactly one searcher exists; never guess between
    # multiple accounts.
    op.execute(
        sa.text(
            """
            UPDATE searches
            SET account_id = (
                SELECT id FROM avito_accounts WHERE role = 'searcher'
            )
            WHERE account_id IS NULL
              AND (SELECT count(*) FROM avito_accounts WHERE role = 'searcher') = 1
            """
        )
    )
    # Preserve our SKU rows, but remove market listings that have no source
    # search and are not represented as one of our own Avito items.
    op.execute(
        sa.text(
            """
            DELETE FROM listing_snapshots AS snapshots
            WHERE NOT EXISTS (SELECT 1 FROM searches s WHERE s.id = snapshots.search_id)
               OR NOT EXISTS (SELECT 1 FROM listings l WHERE l.id = snapshots.listing_id)
               OR (
                 NOT EXISTS (
                   SELECT 1 FROM search_listings links
                   WHERE links.listing_id = snapshots.listing_id
                 )
                 AND NOT EXISTS (
                   SELECT 1 FROM our_listings ours
                   WHERE ours.avito_item_id = snapshots.listing_id
                 )
               )
            """
        )
    )
    op.create_foreign_key(
        "fk_listing_snapshots_search_id", "listing_snapshots", "searches",
        ["search_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_listing_snapshots_listing_id", "listing_snapshots", "listings",
        ["listing_id"], ["id"], ondelete="CASCADE",
    )
    op.execute(
        sa.text(
            """
            DELETE FROM listings AS listings
            WHERE NOT EXISTS (
                SELECT 1 FROM search_listings links WHERE links.listing_id = listings.id
            )
            AND NOT EXISTS (
                SELECT 1 FROM our_listings ours WHERE ours.avito_item_id = listings.id
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE listing_edits AS edits
            SET account_id = ours.account_id
            FROM our_listings AS ours
            WHERE edits.sku = ours.sku
              AND edits.account_id IS NULL
              AND ours.account_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    # Data cleanup is intentionally irreversible.
    op.drop_constraint("fk_listing_snapshots_listing_id", "listing_snapshots", type_="foreignkey")
    op.drop_constraint("fk_listing_snapshots_search_id", "listing_snapshots", type_="foreignkey")
