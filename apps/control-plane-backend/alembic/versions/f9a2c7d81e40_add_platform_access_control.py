# SPDX-License-Identifier: Apache-2.0
"""Add platform admission state.

Revision ID: f9a2c7d81e40
Revises: b4e8d2a9c613
"""

import sqlalchemy as sa
from alembic import op

revision = "f9a2c7d81e40"  # pragma: allowlist secret
down_revision = "b4e8d2a9c613"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("admission_attribute", sa.JSON(), nullable=True),
        sa.Column("admission_claim_path", sa.String(64), nullable=True),
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
    op.add_column(
        "teammetadata", sa.Column("enrollment_token_hash", sa.String(64), nullable=True)
    )
    op.create_index(
        "ix_teammetadata_enrollment_token_hash",
        "teammetadata",
        ["enrollment_token_hash"],
        unique=True,
    )
    op.create_table(
        "platform_access_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("policy_fingerprint", sa.String(64), nullable=False),
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
    op.drop_index("ix_teammetadata_enrollment_token_hash", table_name="teammetadata")
    for name in (
        "enrollment_token_hash",
        "platform_access_free",
        "platform_access_allowed",
    ):
        op.drop_column("teammetadata", name)
    for name in (
        "admission_conflicted",
        "admission_expires_at",
        "admission_issued_at",
        "admission_claim_path",
        "admission_attribute",
    ):
        op.drop_column("users", name)
