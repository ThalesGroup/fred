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

"""Repair pod defaults in databases that already applied the earlier PR revision.

Revision ID: 7e0d93f21c6a
Revises: b42e9f19d4ca
Create Date: 2026-10-23 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7e0d93f21c6a"  # pragma: allowlist secret
down_revision: Union[str, Sequence[str], None] = (
    "b42e9f19d4ca"  # pragma: allowlist secret
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "model_discovery_source_state" not in tables:
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
    elif "revision" not in {
        column["name"]
        for column in inspector.get_columns("model_discovery_source_state")
    }:
        op.add_column(
            "model_discovery_source_state",
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        )
    if "pod_chat_default" not in tables:
        op.create_table(
            "pod_chat_default",
            sa.Column("runtime_id", sa.String(length=160), primary_key=True),
            sa.Column("profile_id", sa.String(length=256), nullable=True),
            sa.Column("fallback_profile_id", sa.String(length=256), nullable=True),
            sa.Column("updated_by", sa.String(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    elif "fallback_profile_id" not in {
        column["name"] for column in inspector.get_columns("pod_chat_default")
    }:
        op.add_column(
            "pod_chat_default",
            sa.Column("fallback_profile_id", sa.String(length=256), nullable=True),
        )
    if "platform_model_fallback" in tables:
        op.drop_table("platform_model_fallback")


def downgrade() -> None:
    # The preceding revision owns the final pod-default schema.
    pass
