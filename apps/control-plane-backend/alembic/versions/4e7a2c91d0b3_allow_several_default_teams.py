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

"""allow several default teams for new users

Replaces the platform_default_team singleton with platform_default_teams, one
row per team. The current default team, if any, is carried over. Downgrading
keeps only the most recently saved team, since the singleton holds one.

Revision ID: 4e7a2c91d0b3
Revises: 9c41e7b2d58a
Create Date: 2026-09-14 13:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4e7a2c91d0b3"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "9c41e7b2d58a"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "platform_default_teams",
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("team_id"),
    )
    op.execute(
        "INSERT INTO platform_default_teams (team_id, updated_by, updated_at) "
        "SELECT team_id, updated_by, updated_at FROM platform_default_team"
    )
    op.drop_table("platform_default_team")


def downgrade() -> None:
    """Downgrade schema."""
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
    op.execute(
        "INSERT INTO platform_default_team (id, team_id, updated_by, updated_at) "
        "SELECT 'default', team_id, updated_by, updated_at FROM platform_default_teams "
        "ORDER BY updated_at DESC, team_id LIMIT 1"
    )
    op.drop_table("platform_default_teams")
