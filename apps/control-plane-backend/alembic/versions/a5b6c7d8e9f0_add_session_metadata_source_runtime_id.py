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

"""add session_metadata.source_runtime_id

Erasure resolves a session's runtime by re-reading the (mutable-lifetime)
agent_instance row for its source_runtime_id. Once the instance is deleted
that lookup returns None forever, permanently blocking runtime checkpoint/
history erasure (issue #2089, FRED-2.0.2-RGPD-READY-RFC §7). source_runtime_id
is immutable after instance creation and names a platform-config-level
runtime catalog entry, not instance-row data, so capturing it once on the
session at create_session time removes the dependency on the instance row
still existing. Backfilled here for every row whose agent_instance_id still
resolves to a live instance; rows whose instance was already deleted before
this migration stay NULL (unrecoverable regardless of fix shape — the
instance -> source mapping is already gone).

Revision ID: a5b6c7d8e9f0
Revises: a4b5c6d7e8f9
Create Date: 2026-07-24 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5b6c7d8e9f0"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "a4b5c6d7e8f9"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "session_metadata",
        sa.Column("source_runtime_id", sa.String(), nullable=True),
    )
    # Backfill from agent_instance for every session whose instance is still
    # enrolled — the common case, since this bug only affects instances
    # deleted before the fix ships.
    op.execute(
        """
        UPDATE session_metadata
        SET source_runtime_id = agent_instance.source_runtime_id
        FROM agent_instance
        WHERE session_metadata.agent_instance_id = agent_instance.agent_instance_id
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("session_metadata", "source_runtime_id")
