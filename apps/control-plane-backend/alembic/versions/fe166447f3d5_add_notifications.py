# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""add in-app notifications

Creates `notifications` (one row per recipient) and adds the nullable
`agent_marketplace_entry.published_by`. Existing entries keep no publisher.

Revision ID: fe166447f3d5
Revises: c9acb7dd3ad0
Create Date: 2026-10-22 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fe166447f3d5"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c9acb7dd3ad0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

__all__ = [
    "branch_labels",
    "depends_on",
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("recipient_id", sa.String(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("team_id", sa.String(), nullable=True),
        sa.Column(
            "group_key",
            sa.String(length=255),
            nullable=False,
            comment="Shared by every row about the same subject: dedupe and resolve.",
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("handled_by", sa.String(), nullable=True),
        sa.Column(
            "handled_by_name",
            sa.String(length=255),
            nullable=True,
            comment="Display snapshot of who handled the group, as in payload.",
        ),
        sa.Column("handled_outcome", sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_recipient_created",
        "notifications",
        ["recipient_id", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_recipient_unseen",
        "notifications",
        ["recipient_id"],
        unique=False,
        postgresql_where=sa.text("seen_at IS NULL"),
        sqlite_where=sa.text("seen_at IS NULL"),
    )
    op.create_index(
        op.f("ix_notifications_expires_at"),
        "notifications",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "uq_notifications_open_group",
        "notifications",
        ["group_key", "recipient_id"],
        unique=True,
        postgresql_where=sa.text("handled_at IS NULL"),
        sqlite_where=sa.text("handled_at IS NULL"),
    )
    with op.batch_alter_table("agent_marketplace_entry") as batch:
        batch.add_column(
            sa.Column(
                "published_by",
                sa.String(),
                nullable=True,
                comment="Uid of the last publisher; null for entries published "
                "before it was recorded.",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("agent_marketplace_entry") as batch:
        batch.drop_column("published_by")
    op.drop_index("uq_notifications_open_group", table_name="notifications")
    op.drop_index(op.f("ix_notifications_expires_at"), table_name="notifications")
    op.drop_index("ix_notifications_recipient_unseen", table_name="notifications")
    op.drop_index("ix_notifications_recipient_created", table_name="notifications")
    op.drop_table("notifications")
