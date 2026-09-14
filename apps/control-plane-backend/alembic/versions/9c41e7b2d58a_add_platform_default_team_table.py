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

"""add platform_default_team table

The team every user joins on first GCU acceptance, chosen by a platform admin.
At most one row, keyed `id="default"` and CHECK-enforced like platform_prompt.
No row is seeded: absence means no default team.

Revision ID: 9c41e7b2d58a
Revises: d3f8a2c6e174
Create Date: 2026-09-14 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c41e7b2d58a"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d3f8a2c6e174"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "platform_default_team",
        sa.Column("id", sa.String(), nullable=False, server_default="default"),
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("id = 'default'", name="ck_platform_default_team_singleton"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("platform_default_team")
