"""Close historical actions that cannot be safely attributed.

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE listing_edits AS edits
            SET status = 'failed',
                error = 'закрыто при проверке целостности: у SKU не был указан аккаунт-продавец'
            FROM our_listings AS ours
            WHERE edits.sku = ours.sku
              AND ours.account_id IS NULL
              AND edits.status IN ('draft', 'approved', 'applying', 'reverting')
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE agent_decisions
            SET status = 'rejected',
                comment = 'устаревший консенсус без источников evidence закрыт при проверке целостности'
            WHERE status = 'proposed'
              AND NOT (payload ? 'sources')
            """
        )
    )


def downgrade() -> None:
    pass
