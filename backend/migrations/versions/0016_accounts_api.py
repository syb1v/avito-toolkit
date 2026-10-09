"""accounts: API credentials

Revision ID: 0016_accounts_api
Revises: 0015_edit_ai_summary
Create Date: 2026-10-09
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_accounts_api"
down_revision = "0015_edit_ai_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("avito_accounts", sa.Column("api_client_id", sa.String(128)))
    op.add_column("avito_accounts", sa.Column("api_client_secret", sa.Text()))
    op.add_column("avito_accounts", sa.Column("api_user_id", sa.BigInteger()))


def downgrade() -> None:
    op.drop_column("avito_accounts", "api_user_id")
    op.drop_column("avito_accounts", "api_client_secret")
    op.drop_column("avito_accounts", "api_client_id")
