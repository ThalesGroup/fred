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

"""add team_metadata visibility

TEAM-10 (FRED-TEAM-CONFIG-RFC.md §5.1.2): adds a `visibility` column
(`TeamVisibility`: `public`/`private`) that gates marketplace
discoverability, independent of `joining_mode`. Every existing team
backfills to `public` — this preserves today's unconditional marketplace
presence exactly; nothing becomes newly private as a side effect of this
migration.

Revision ID: 8092a626d4d0
Revises: 9ee7b44b0d57
Create Date: 2026-07-26 22:09:25.272998

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8092a626d4d0"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "9ee7b44b0d57"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "teammetadata",
        sa.Column(
            "visibility",
            sa.String(length=20),
            nullable=False,
            server_default="public",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("teammetadata", "visibility")
