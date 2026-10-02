"""accounts: profile-based Avito accounts with trusted cookies

Revision ID: 0007_accounts
Revises: 0006_descriptions
Create Date: 2026-10-02
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0007_accounts"
down_revision = "0006_descriptions"
branch_labels = None
depends_on = None

DEFAULT_ACCOUNT_NAME = "Основной"


def upgrade() -> None:
    op.create_table(
        "avito_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("profile_dir", sa.Text(), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cookies_at", sa.DateTime(timezone=True)),
        sa.Column("last_check_at", sa.DateTime(timezone=True)),
        sa.Column("last_check_ok", sa.Boolean()),
        sa.Column("last_error", sa.Text()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column("searches", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_searches_account_id",
        "searches",
        "avito_accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_searches_account_id", "searches", ["account_id"])

    default_id = str(uuid.uuid4())
    op.execute(
        sa.text(
            "INSERT INTO avito_accounts (id, name, profile_dir, status, is_default, notes) "
            "VALUES (CAST(:id AS uuid), :name, :profile, 'active', true, "
            "'Существующий профиль автоматизации (BROWSER_USER_DATA_DIR)')"
        ).bindparams(id=default_id, name=DEFAULT_ACCOUNT_NAME, profile=".browser-profile")
    )
    op.execute(
        sa.text(
            "UPDATE searches SET account_id = CAST(:id AS uuid) WHERE account_id IS NULL"
        ).bindparams(id=default_id)
    )


def downgrade() -> None:
    op.drop_index("ix_searches_account_id", table_name="searches")
    op.drop_constraint("fk_searches_account_id", "searches", type_="foreignkey")
    op.drop_column("searches", "account_id")
    op.drop_table("avito_accounts")
