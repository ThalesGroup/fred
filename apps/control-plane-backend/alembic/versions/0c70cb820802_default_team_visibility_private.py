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

"""default team visibility private

#2433: new teams are private by default — a team stays invisible to
non-members until its admin deliberately opts into the marketplace. This
aligns the DB-level `server_default` with the flipped ORM/Pydantic defaults
(`TeamMetadataRow.visibility`, fred-core). The ORM default is what actually
applies on `TeamMetadataStore.create`; the server_default only backs raw SQL
inserts. **No data is touched**: every existing row keeps its stored value —
nothing becomes private as a side effect of this rollout (same stance as
migration 8092a626d4d0 in the other direction).

Revision ID: 0c70cb820802
Revises: 0dd1e72106af
Create Date: 2026-08-26 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0c70cb820802"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "0dd1e72106af"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Batch mode for SQLite compatibility (same pattern as 9ee7b44b0d57 on
    # this table): SQLite has no `ALTER COLUMN ... SET DEFAULT`, so batch
    # recreates the table there; Postgres still gets a plain ALTER.
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "visibility",
            existing_type=sa.String(length=20),
            existing_nullable=False,
            server_default="private",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("teammetadata") as batch_op:
        batch_op.alter_column(
            "visibility",
            existing_type=sa.String(length=20),
            existing_nullable=False,
            server_default="public",
        )
