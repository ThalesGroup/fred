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
"""Add patch-note announcements, their dismissals and the activation history.

The server default backfills every existing announcement as a banner. The
partial unique index keeps at most one patch note enabled. Downgrading deletes
patch notes, which would otherwise come back as broken banners.

Revision ID: cb6f39c6d80c
Revises: aac66348e27b
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "cb6f39c6d80c"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "aac66348e27b"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_PATCH_NOTE = "enabled AND kind = 'patch_note'"


def upgrade() -> None:
    with op.batch_alter_table("platform_announcement") as batch:
        batch.add_column(
            sa.Column(
                "kind",
                sa.String(length=16),
                server_default="banner",
                nullable=False,
                comment="banner | patch_note. A patch note stores its markdown "
                "body in description_long and its plain-text title in title; "
                "description_short stays empty.",
            )
        )
    op.create_index(
        "uq_platform_announcement_active_patch_note",
        "platform_announcement",
        ["kind"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_PATCH_NOTE),
        sqlite_where=sa.text(_ACTIVE_PATCH_NOTE),
    )
    op.create_table(
        "platform_announcement_dismissal",
        sa.Column("announcement_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["announcement_id"], ["platform_announcement.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("announcement_id", "user_id"),
    )
    op.create_table(
        "platform_announcement_activation_event",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("announcement_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column(
            "label",
            sa.JSON(),
            nullable=False,
            comment="Locale → title at event time.",
        ),
        sa.Column(
            "action",
            sa.String(length=16),
            nullable=False,
            comment="activated | deactivated",
        ),
        sa.Column(
            "severity",
            sa.String(length=16),
            nullable=True,
            comment="Banner severity at event time; null for a patch note.",
        ),
        sa.Column("actor_uid", sa.String(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_announcement_activation_event_occurred_at"),
        "platform_announcement_activation_event",
        ["occurred_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_platform_announcement_activation_event_occurred_at"),
        table_name="platform_announcement_activation_event",
    )
    op.drop_table("platform_announcement_activation_event")
    op.drop_table("platform_announcement_dismissal")
    op.execute("DELETE FROM platform_announcement WHERE kind = 'patch_note'")
    op.drop_index(
        "uq_platform_announcement_active_patch_note",
        table_name="platform_announcement",
    )
    with op.batch_alter_table("platform_announcement") as batch:
        batch.drop_column("kind")
