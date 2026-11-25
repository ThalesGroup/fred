# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Fenced preparations owned by the Word library."""

import sqlalchemy as sa
from alembic import op

revision = "w8a1b2c3d4e5"
down_revision = "w7t4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cap_word_template_preparations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("space_id", sa.String(36), nullable=False),
        sa.Column("runtime_id", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempt", sa.String(36)),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("pending_writes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("analysis", sa.Text()),
        sa.Column("object_path", sa.String(255)),
        sa.CheckConstraint("pending_writes >= 0"),
        sa.CheckConstraint("state in ('pending','ready','retired')"),
        sa.CheckConstraint(
            "state <> 'ready' or (analysis is not null and object_path is not null)"
        ),
    )


def downgrade() -> None:
    op.drop_table("cap_word_template_preparations")
