# SPDX-License-Identifier: Apache-2.0
"""Add platform admission state.

Revision ID: f9a2c7d81e40
Revises: aac66348e27b
"""

import sqlalchemy as sa
from alembic import op

revision = "f9a2c7d81e40"  # pragma: allowlist secret
down_revision = "aac66348e27b"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("admission_attribute", sa.JSON(), nullable=True),
        sa.Column("admission_issued_at", sa.Float(), nullable=True),
        sa.Column("admission_expires_at", sa.Float(), nullable=True),
        sa.Column(
            "admission_conflicted",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    ):
        op.add_column("users", column)
    op.add_column(
        "teammetadata",
        sa.Column(
            "platform_access_allowed",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "teammetadata",
        sa.Column(
            "platform_access_free",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_table(
        "platform_access_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "team_id",
            sa.String(),
            sa.ForeignKey("teammetadata.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("token", sa.String(43), nullable=True),
        sa.Column("note", sa.String(512), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opening_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_platform_access_links_team_id", "platform_access_links", ["team_id"]
    )
    op.create_table(
        "platform_access_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy", sa.JSON(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "filtering_enabled", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("t0_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "platform_access_users",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("granted_by", sa.String(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("platform_access_users")
    op.drop_table("platform_access_settings")
    op.drop_table("platform_access_links")
    for name in (
        "platform_access_free",
        "platform_access_allowed",
    ):
        op.drop_column("teammetadata", name)
    for name in (
        "admission_conflicted",
        "admission_expires_at",
        "admission_issued_at",
        "admission_attribute",
    ):
        op.drop_column("users", name)
