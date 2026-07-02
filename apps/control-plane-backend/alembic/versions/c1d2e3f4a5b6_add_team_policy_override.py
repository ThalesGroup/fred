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

"""add team_policy_override table

Stores a per-team retention policy override (one row per team), layered over the
static ops-owned conversation policy catalog. Platform caps; team may only
tighten (FRED-2.0.2-RGPD-READY-RFC §3.B).

Revision ID: c1d2e3f4a5b6
Revises: e7f8a9b0c1d2
Create Date: 2026-06-30 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "e7f8a9b0c1d2"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "team_policy_override",
        sa.Column("team_id", sa.String(), nullable=False),
        sa.Column("team_delete_grace", sa.String(), nullable=True),
        sa.Column("max_idle", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("team_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("team_policy_override")
