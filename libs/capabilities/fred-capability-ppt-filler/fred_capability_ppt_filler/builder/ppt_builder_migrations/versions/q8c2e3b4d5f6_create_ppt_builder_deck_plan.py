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

"""create cap_ppt_builder_deck_plan table

The last deck plan the build tool evaluated, per conversation and agent
instance: the base a later partial change applies to. No foreign keys.

Revision ID: q8c2e3b4d5f6
Revises: p7b1d2a3c4e5
Create Date: 2026-10-07 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q8c2e3b4d5f6"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "p7b1d2a3c4e5"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "cap_ppt_builder_deck_plan",
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("agent_instance_id", sa.String(length=128), nullable=False),
        sa.Column("plan_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id", "agent_instance_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("cap_ppt_builder_deck_plan")
