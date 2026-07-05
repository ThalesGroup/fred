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

"""add team_metadata retention columns

Per-team conversation retention (CTRLP-12 rev. 2 / Phase R,
FRED-2.0.2-RGPD-READY-RFC §3.B): the values live on the existing team_metadata
store — a per-team setting is a field here, never its own table. Replaces the
removed `team_policy_override` table. All three columns are nullable; None means
the team inherits the platform cap (unset ⇒ immediate delete).

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-07-04 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3f4a5b6c7d8"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "d2e3f4a5b6c7"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "teammetadata",
        sa.Column("team_delete_grace", sa.String(), nullable=True),
    )
    op.add_column(
        "teammetadata",
        sa.Column("max_idle", sa.String(), nullable=True),
    )
    op.add_column(
        "teammetadata",
        sa.Column("retention_updated_by", sa.String(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("teammetadata", "retention_updated_by")
    op.drop_column("teammetadata", "max_idle")
    op.drop_column("teammetadata", "team_delete_grace")
