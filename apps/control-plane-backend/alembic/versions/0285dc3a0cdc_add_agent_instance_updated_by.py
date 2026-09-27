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

"""add agent_instance.updated_by audit column

Revision ID: 0285dc3a0cdc
Revises: f824bb94e60d
Create Date: 2026-07-20

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0285dc3a0cdc"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f824bb94e60d"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the nullable `updated_by` audit column (#1952).

    Why:
        `created_by` records who enrolled the instance but edits were
        anonymous. `updated_by` stamps the last editing user; NULL means the
        instance was never user-edited (seed/startup saves have no acting
        user).

    How to use:
        `alembic upgrade head`. A plain nullable ADD COLUMN, so it is
        SQLite-compatible without a batch rewrite.
    """

    op.add_column(
        "agent_instance",
        sa.Column(
            "updated_by",
            sa.String(),
            nullable=True,
            comment=(
                "Uid of the last user who edited the instance (#1952). NULL "
                "when never user-edited (seed/startup saves have no acting "
                "user)."
            ),
        ),
    )


def downgrade() -> None:
    """Drop the `updated_by` column."""

    op.drop_column("agent_instance", "updated_by")
