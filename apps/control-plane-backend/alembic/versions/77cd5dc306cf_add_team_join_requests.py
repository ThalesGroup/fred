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

"""add team join requests

Creates `team_join_requests` for the opt-in `on_request` access mode. No
existing row changes: every team keeps its mode. The downgrade turns
`on_request` teams back into `invite_only`, which the older code knows.

Revision ID: 77cd5dc306cf
Revises: fe166447f3d5
Create Date: 2026-10-22 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "77cd5dc306cf"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "fe166447f3d5"  # pragma: allowlist secret
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
        "team_join_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("requester_id", sa.String(), nullable=False),
        sa.Column(
            "requester_name",
            sa.String(length=255),
            nullable=False,
            comment="Display snapshot taken when asking.",
        ),
        sa.Column("message", sa.String(length=280), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="30 days after asking while pending, 7 days after a refusal.",
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "team_id", "requester_id", name="uq_team_join_requests_team_requester"
        ),
    )
    op.create_index(
        op.f("ix_team_join_requests_requester_id"),
        "team_join_requests",
        ["requester_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_team_join_requests_expires_at"),
        "team_join_requests",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE teammetadata SET joining_mode = 'invite_only' "
        "WHERE joining_mode = 'on_request'"
    )
    op.drop_index(
        op.f("ix_team_join_requests_expires_at"), table_name="team_join_requests"
    )
    op.drop_index(
        op.f("ix_team_join_requests_requester_id"), table_name="team_join_requests"
    )
    op.drop_table("team_join_requests")
