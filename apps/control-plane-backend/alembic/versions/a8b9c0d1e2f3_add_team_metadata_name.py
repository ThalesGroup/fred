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

"""add team_metadata name column

AUTHZ-05 review item 9 (RFC FRED-AUTHORIZATION-TARGET-MODEL-RFC.md Part 6
§29-32): a team is no longer a Keycloak group — it is a `team_metadata` row
plus its OpenFGA relations. This adds the `name` column that makes the store
self-sufficient for team identity. No backfill: this lands on a fresh
deployment with zero pre-existing teams (translating already-live
Keycloak-group-backed teams is a distinct, separately tracked operational
concern, RFC §29).

Revision ID: a8b9c0d1e2f3
Revises: f4a5b6c7d8e9
Create Date: 2026-07-10 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "f4a5b6c7d8e9"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "teammetadata",
        sa.Column("name", sa.String(length=180), nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("teammetadata", "name")
