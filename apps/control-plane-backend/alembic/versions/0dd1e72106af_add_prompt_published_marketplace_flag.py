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

"""add prompt published marketplace flag

PROMPT-06 (prompts marketplace): adds a boolean `published` column to the
`prompt` table. When true, the team's own prompt row is surfaced live in the
global prompts marketplace ("Prompts de la communauté") — a visibility flag,
not a snapshot: edits and the shared usage counter propagate immediately.
Every existing prompt backfills to `false` (unpublished), so the migration
changes no prompt's visibility.

Revision ID: 0dd1e72106af
Revises: d5c9a1b73e60
Create Date: 2026-08-10 17:23:08.650174

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0dd1e72106af"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d5c9a1b73e60"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "prompt",
        sa.Column(
            "published",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("prompt", "published")
