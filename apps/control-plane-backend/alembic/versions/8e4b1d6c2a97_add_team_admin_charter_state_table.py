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

"""add team_admin_charter_state table

A single row holding the charter version team admin relations were last
reconciled against, so startup only rewrites relations when it changes.

Revision ID: 8e4b1d6c2a97
Revises: 5d2a8c7e1f43
Create Date: 2026-09-15 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8e4b1d6c2a97"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "5d2a8c7e1f43"  # pragma: allowlist secret
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
        "team_admin_charter_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("applied_version", sa.String(), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("team_admin_charter_state")
