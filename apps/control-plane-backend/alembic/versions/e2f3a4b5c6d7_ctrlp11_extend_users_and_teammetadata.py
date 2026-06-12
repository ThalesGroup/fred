"""CTRLP-11: extend users and add name to teammetadata

Revision ID: e2f3a4b5c6d7
Revises: be753abe25d7
Create Date: 2026-06-11

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e2f3a4b5c6d7"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(255), nullable=False))
    op.add_column("users", sa.Column("email", sa.String(255), nullable=False))
    op.add_column("users", sa.Column("first_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "users",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    op.add_column("teammetadata", sa.Column("name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("teammetadata", "name")

    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "created_at")
    op.drop_column("users", "enabled")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")
    op.drop_column("users", "email")
    op.drop_column("users", "username")
