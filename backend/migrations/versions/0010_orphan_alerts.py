"""delete alerts of removed searches

Revision ID: 0010_orphan_alerts
Revises: 0009_account_roles
Create Date: 2026-10-03
"""

from alembic import op

revision = "0010_orphan_alerts"
down_revision = "0009_account_roles"
branch_labels = None
depends_on = None

DELETE_ORPHANS = """
DELETE FROM alerts a
WHERE NOT EXISTS (
    SELECT 1 FROM searches s
    WHERE s.id::text = a.payload->>'search_id'
)
"""


def upgrade() -> None:
    op.execute(DELETE_ORPHANS)


def downgrade() -> None:
    pass
