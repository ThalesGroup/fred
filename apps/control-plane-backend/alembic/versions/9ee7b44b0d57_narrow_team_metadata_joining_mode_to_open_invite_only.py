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

"""narrow team_metadata joining_mode to open/invite_only

TEAM-09 amendment (FRED-TEAM-CONFIG-RFC.md §5.1.1, 2026-07-26): `JoiningMode`
drops `request_only` and `closed`, leaving `open` / `invite_only`.
`request_only` depended on a notification system that was never built and
shipped with its marketplace affordance permanently disabled; `closed` never
enforced anything `invite_only` didn't — the two differed only in
marketplace copy. Both remaining values keep their original meaning.

Every row currently in `request_only` or `closed` is backfilled to
`invite_only` — the conservative mapping: no team becomes self-service
`open` as a side effect of this migration. The column's `server_default`
moves from `request_only` (set by `a4b5c6d7e8f9`) to `invite_only`, matching
the new default for freshly created teams.

Revision ID: 9ee7b44b0d57
Revises: a5b6c7d8e9f0
Create Date: 2026-07-26 19:05:37.045450

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9ee7b44b0d57"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a5b6c7d8e9f0"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TEAM_METADATA = sa.table(
    "teammetadata",
    sa.column("joining_mode", sa.String),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        _TEAM_METADATA.update()
        .where(_TEAM_METADATA.c.joining_mode.in_(["request_only", "closed"]))
        .values(joining_mode="invite_only")
    )
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "joining_mode",
            existing_type=sa.String(length=20),
            server_default="invite_only",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "joining_mode",
            existing_type=sa.String(length=20),
            server_default="request_only",
        )
    # Data backfilled to `invite_only` on upgrade cannot be distinguished
    # back into `request_only` vs `closed` — downgrade only restores the
    # column default, not the original per-row values.
