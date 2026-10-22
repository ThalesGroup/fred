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

"""Store platform model display-name overrides.

Revision ID: b42e9f19d4ca
Revises: c9acb7dd3ad0
Create Date: 2026-10-22 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b42e9f19d4ca"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "c9acb7dd3ad0"  # pragma: allowlist secret
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
    op.create_table(
        "model_display_name_override",
        sa.Column("model_capability_id", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "model_discovery_source_state",
        sa.Column("source_id", sa.String(length=64), primary_key=True),
        sa.Column("yaml_url", sa.String(length=2048), nullable=False),
        sa.Column("override_url", sa.String(length=2048), nullable=True),
        sa.Column("active_url", sa.String(length=2048), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inventory_json", sa.Text(), nullable=False),
        sa.Column("removed_json", sa.Text(), nullable=False),
        sa.Column("new_ids_json", sa.Text(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
    )
    op.create_table(
        "platform_model_fallback",
        sa.Column("model_capability", sa.String(), primary_key=True),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "model_capability = 'chat'", name="ck_platform_model_fallback_chat_only"
        ),
    )


def downgrade() -> None:
    op.drop_table("platform_model_fallback")
    op.drop_table("model_discovery_source_state")
    op.drop_table("model_display_name_override")
