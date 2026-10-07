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

"""add agent_instance.suspension_detail (capability readiness)

A capability whose save starts background work reports readiness; while it is
pending or after it failed the instance is suspended with
``capability_pending``, and a failure's message is stored in the new nullable
``suspension_detail`` column. The ``suspension_reason`` comment lists the new
value.

Revision ID: b8e1f4a2c6d9
Revises: aac66348e27b
Create Date: 2026-10-05 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e1f4a2c6d9"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "aac66348e27b"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_REASON_COMMENT_BEFORE = (
    "Platform-forced suspension reason (#1975, RFC §3.9). NULL = not "
    "suspended; else one of capability_unavailable / "
    "capability_access_revoked / capability_config_invalid. Distinct "
    "from the editor's `enabled` toggle."
)
_REASON_COMMENT_AFTER = (
    "Platform-forced suspension reason (#1975, RFC §3.9). NULL = not "
    "suspended; else one of capability_unavailable / "
    "capability_access_revoked / capability_config_invalid / "
    "capability_pending. Distinct from the editor's `enabled` toggle."
)
_DETAIL_COMMENT = (
    "Plain-language failure carried with suspension_reason="
    "capability_pending when a capability reported its preparation "
    "failed. NULL otherwise."
)


def upgrade() -> None:
    with op.batch_alter_table("agent_instance") as batch_op:
        batch_op.add_column(
            sa.Column(
                "suspension_detail",
                sa.Text(),
                nullable=True,
                comment=_DETAIL_COMMENT,
            )
        )
        batch_op.alter_column(
            "suspension_reason",
            existing_type=sa.VARCHAR(length=64),
            existing_nullable=True,
            comment=_REASON_COMMENT_AFTER,
            existing_comment=_REASON_COMMENT_BEFORE,
        )


def downgrade() -> None:
    # Older control planes parse suspension_reason into an enum without this
    # value and would fail listing the team's agents, so lift these first.
    op.execute(
        sa.text(
            "UPDATE agent_instance SET suspension_reason = NULL "
            "WHERE suspension_reason = 'capability_pending'"
        )
    )
    with op.batch_alter_table("agent_instance") as batch_op:
        batch_op.alter_column(
            "suspension_reason",
            existing_type=sa.VARCHAR(length=64),
            existing_nullable=True,
            comment=_REASON_COMMENT_BEFORE,
            existing_comment=_REASON_COMMENT_AFTER,
        )
        batch_op.drop_column("suspension_detail")
