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

"""add team_metadata joining_mode, drop is_private

TEAM-09 (FRED-TEAM-CONFIG-RFC.md §5.1.1): replaces the boolean `is_private`
with a `JoiningMode` enum (open / request_only / invite_only / closed) that
gates only whether/how a user can become a member — marketplace visibility is
now unconditional for every team (see `RebacEngine.ensure_team_public_relations`).

Every existing team migrates to `request_only` regardless of its prior
`is_private` value: `is_private` never actually gated the marketplace's
mailto-based join before this change (joining was always "send an email and
ask", for private and non-private teams alike), so `request_only` is the only
mapping that changes no team's real-world joinability on migration day. The
`server_default` below backfills every existing row in the same statement —
no separate UPDATE needed.

Revision ID: a4b5c6d7e8f9
Revises: 0285dc3a0cdc
Create Date: 2026-07-23 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "0285dc3a0cdc"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "teammetadata",
        sa.Column(
            "joining_mode",
            sa.String(length=20),
            nullable=False,
            server_default="request_only",
        ),
    )
    op.drop_column("teammetadata", "is_private")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "teammetadata",
        sa.Column(
            "is_private",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.drop_column("teammetadata", "joining_mode")
