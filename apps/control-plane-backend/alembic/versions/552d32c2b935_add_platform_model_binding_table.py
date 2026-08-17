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

"""add platform_model_binding table

Platform-operator-asserted concrete model binding for the `chat` capability
only — at most one row ever exists, always keyed
`model_capability="chat"`, enforced by a CHECK constraint so the normal
store/service path structurally cannot insert a `language`/`embedding`/
`image` row. Overrides whatever every pod would otherwise resolve locally
for `chat` (`fred_sdk.contracts.context.ModelBinding`). Resolved trusted,
server-side, on the runtime's own per-turn `ManagedAgentRuntimeBinding`
lookup (`BoundRuntimeContext.platform_chat_model_binding`) — never a
client-forwarded `RuntimeContext` field.

No natural "off" sentinel for a `(provider, name)` pair, unlike
`model_reasoning`'s boolean column — "unset" is row absence, so no backfill
and no default row is written here.

Revision ID: 552d32c2b935
Revises: 7fde1b42d5d0
Create Date: 2026-08-14 07:37:46.474847

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "552d32c2b935"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "7fde1b42d5d0"  # pragma: allowlist secret
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
        "platform_model_binding",
        sa.Column(
            "model_capability", sa.String(), nullable=False, server_default="chat"
        ),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("model_capability"),
        sa.CheckConstraint(
            "model_capability = 'chat'",
            name="ck_platform_model_binding_chat_only",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("platform_model_binding")
