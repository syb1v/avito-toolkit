"""Store structured identity evidence for market matches.

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("product_market_matches", sa.Column("identity", sa.JSON(), nullable=True))
    op.add_column("product_market_matches", sa.Column("conflict_reasons", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("product_market_matches", "conflict_reasons")
    op.drop_column("product_market_matches", "identity")
