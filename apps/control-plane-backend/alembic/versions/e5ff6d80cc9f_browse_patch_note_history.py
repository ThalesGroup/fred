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

"""Patch notes: any number visible, a manual order, a per-user seen marker.

The enabled patch note stays the only visible one. This revision records no
announcement, so no user gets a dialog; the next one (a6c1d94e27b3) freezes the
enabled patch notes as a first package, pending for nobody. Earlier "Don't show again"
choices are discarded with their table. Downgrading keeps the top visible
patch note enabled and drops the announcement events the older code cannot read.

Revision ID: e5ff6d80cc9f
Revises: 9f6d3c2a1b08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5ff6d80cc9f"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "9f6d3c2a1b08"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_PATCH_NOTE = "enabled AND kind = 'patch_note'"
_ACTIONS_BEFORE = "activated | deactivated"
_ACTIONS_AFTER = "activated | deactivated | announced | unannounced"


def _set_action_comment(comment: str, existing: str) -> None:
    with op.batch_alter_table("platform_announcement_activation_event") as batch:
        batch.alter_column(
            "action",
            existing_type=sa.String(length=16),
            existing_nullable=False,
            comment=comment,
            existing_comment=existing,
        )


def upgrade() -> None:
    op.drop_index(
        "uq_platform_announcement_active_patch_note",
        table_name="platform_announcement",
    )
    with op.batch_alter_table("platform_announcement") as batch:
        batch.add_column(
            sa.Column(
                "position",
                sa.Integer(),
                nullable=True,
                comment="Patch note only: its place in the administrator's "
                "order, 1 at the top. Null for a banner.",
            )
        )
    connection = op.get_bind()
    newest_first = connection.execute(
        sa.text(
            "SELECT id FROM platform_announcement WHERE kind = 'patch_note' "
            "ORDER BY created_at DESC, id DESC"
        )
    ).scalars()
    for position, announcement_id in enumerate(newest_first.all(), start=1):
        connection.execute(
            sa.text("UPDATE platform_announcement SET position = :p WHERE id = :id"),
            {"p": position, "id": announcement_id},
        )
    op.drop_table("platform_announcement_dismissal")
    op.create_table(
        "platform_announcement_seen",
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("announcement_event_id", sa.String(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    _set_action_comment(_ACTIONS_AFTER, _ACTIONS_BEFORE)


def downgrade() -> None:
    _set_action_comment(_ACTIONS_BEFORE, _ACTIONS_AFTER)
    op.execute(
        "DELETE FROM platform_announcement_activation_event "
        "WHERE action IN ('announced', 'unannounced')"
    )
    op.drop_table("platform_announcement_seen")
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
    # The index allows one enabled patch note: keep the one users open on.
    connection = op.get_bind()
    visible = connection.execute(
        sa.text(
            "SELECT id FROM platform_announcement "
            "WHERE kind = 'patch_note' AND enabled "
            "ORDER BY position ASC, created_at DESC, id DESC"
        )
    ).scalars()
    for announcement_id in visible.all()[1:]:
        connection.execute(
            sa.text("UPDATE platform_announcement SET enabled = :off WHERE id = :id"),
            {"off": False, "id": announcement_id},
        )
    with op.batch_alter_table("platform_announcement") as batch:
        batch.drop_column("position")
    op.create_index(
        "uq_platform_announcement_active_patch_note",
        "platform_announcement",
        ["kind"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_PATCH_NOTE),
        sqlite_where=sa.text(_ACTIVE_PATCH_NOTE),
    )
