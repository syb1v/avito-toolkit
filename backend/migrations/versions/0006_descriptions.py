"""listing description and flag category

Revision ID: 0006_descriptions
Revises: 0005_moderation
Create Date: 2026-10-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_descriptions"
down_revision = "0005_moderation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("listings", sa.Column("description_fetched_at", sa.DateTime(timezone=True)))
    op.add_column("listings", sa.Column("flag_category", sa.String(32), nullable=True))
    op.create_index("ix_listings_flag_category", "listings", ["flag_category"])


def downgrade() -> None:
    op.drop_index("ix_listings_flag_category", table_name="listings")
    op.drop_column("listings", "flag_category")
    op.drop_column("listings", "description_fetched_at")
    op.drop_column("listings", "description")
