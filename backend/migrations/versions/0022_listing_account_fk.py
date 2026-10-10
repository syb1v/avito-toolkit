"""Add authoritative seller FK to our listings.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("our_listings", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_index("ix_our_listings_account_id", "our_listings", ["account_id"])
    op.create_foreign_key(
        "fk_our_listings_account_id",
        "our_listings",
        "avito_accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.execute(
        sa.text(
            """
            UPDATE our_listings AS listings
            SET account_id = accounts.id
            FROM avito_accounts AS accounts
            WHERE listings.account_id IS NULL
              AND listings.account = accounts.name
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_our_listings_account_id", "our_listings", type_="foreignkey")
    op.drop_index("ix_our_listings_account_id", table_name="our_listings")
    op.drop_column("our_listings", "account_id")
