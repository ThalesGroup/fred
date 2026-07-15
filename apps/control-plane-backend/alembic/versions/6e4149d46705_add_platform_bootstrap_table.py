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

"""add platform bootstrap table

AUTHZ-07 (RFC FRED-AUTHORIZATION-TARGET-MODEL-RFC.md Part 8, §42.3): durable
"root bootstrap has completed" marker. Deliberately not derived from live
OpenFGA state (a `lookup_subjects` count of `platform_admin` on
`organization:fred`) — removing every `platform_admin` later must not
silently reopen root bootstrap for anyone who still holds the deploy-time
secret. A single fixed-id row (`id = "platform"`) is the entire table: it
either exists (bootstrap is permanently done) or it does not (bootstrap has
never run). No backfill: this lands on a fresh deployment that has never run
root bootstrap before this table existed.

Note: autogenerate also detected unrelated `metadata`/`tag` tables (from
`fred_core.documents.document_models`, imported into this app's Alembic env
for shared metadata but not owned by control-plane-backend's own migration
chain) — dropped from this revision; out of scope for AUTHZ-07.

Revision ID: 6e4149d46705
Revises: a8b9c0d1e2f3
Create Date: 2026-07-14 05:41:27.920683

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6e4149d46705"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a8b9c0d1e2f3"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "platformbootstrap",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_by", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("platformbootstrap")
