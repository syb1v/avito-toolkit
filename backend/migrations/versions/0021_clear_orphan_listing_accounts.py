"""Clear denormalized listing references to deleted accounts.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE our_listings AS listings
            SET account = NULL
            WHERE listings.account IS NOT NULL
              AND NOT EXISTS (
                SELECT 1 FROM avito_accounts AS accounts
                WHERE accounts.name = listings.account
              )
            """
        )
    )


def downgrade() -> None:
    # Deleted account names cannot be reconstructed safely.
    pass
