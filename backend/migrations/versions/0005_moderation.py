"""listing moderation flags

Revision ID: 0005_moderation
Revises: 0004_account
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005_moderation"
down_revision = "0004_account"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column("is_flagged", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("listings", sa.Column("flag_reasons", postgresql.JSONB(), nullable=True))
    op.add_column("listings", sa.Column("relevance_score", sa.Float(), nullable=True))
    op.add_column(
        "listings", sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index("ix_listings_is_flagged", "listings", ["is_flagged"])


def downgrade() -> None:
    op.drop_index("ix_listings_is_flagged", table_name="listings")
    op.drop_column("listings", "moderated_at")
    op.drop_column("listings", "relevance_score")
    op.drop_column("listings", "flag_reasons")
    op.drop_column("listings", "is_flagged")
