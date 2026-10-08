# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Add explicit organization assignment; newcomers remain unassigned.

Revision ID: cd32e50f12b8
Revises: bc21d49e01a7
"""

import sqlalchemy as sa
from alembic import op

revision = "cd32e50f12b8"
down_revision = "bc21d49e01a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("organization_id", sa.String(), nullable=True))
        batch.add_column(
            sa.Column(
                "organization_kind",
                sa.String(20),
                nullable=False,
                server_default="organization",
            )
        )
        batch.create_check_constraint(
            "ck_users_organization_kind", "organization_kind = 'organization'"
        )
        batch.create_foreign_key(
            "fk_users_organization",
            "space",
            ["organization_id", "organization_kind"],
            ["id", "kind"],
        )
        batch.create_index("ix_users_organization_id", ["organization_id"])


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_organization_id")
        batch.drop_constraint("fk_users_organization", type_="foreignkey")
        batch.drop_constraint("ck_users_organization_kind", type_="check")
        batch.drop_column("organization_kind")
        batch.drop_column("organization_id")
