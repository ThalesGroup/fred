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

"""add knowledge_base_definitions

Revision ID: c1e4f70a2b95
Revises: 7b3f5e1a9c20
Create Date: 2026-09-11

A Knowledge Base definition exists because its image published a declaration:
there is no deployment-configuration entry for one, so this table is the whole
record Fred holds. `client_id` is bound by the first publication and every
later one must present the same client.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1e4f70a2b95"  # pragma: allowlist secret
down_revision: Union[str, None] = "7b3f5e1a9c20"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Two tables, because ownership is a fact about a prefix, not about each
    # definition: one row per prefix makes a concurrent first claim collide in
    # PostgreSQL instead of in application code.
    op.create_table(
        "knowledge_base_prefixes",
        sa.Column("prefix", sa.String(length=256), nullable=False),
        sa.Column(
            "client_id",
            sa.String(length=255),
            nullable=False,
            comment=(
                "Confidential M2M client that claimed this prefix first. Every "
                "later publication under it is checked against this value."
            ),
        ),
        sa.Column(
            "subject",
            sa.String(length=255),
            nullable=False,
            comment=(
                "Service account the claiming client authenticates as (`sub`). "
                "A prefix is bound to the client, but only this identity can be "
                "named as a relation's subject, so creating an instance reads it "
                "here instead of asking Keycloak's admin API which account backs "
                "a client."
            ),
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("prefix"),
    )
    op.create_table(
        "knowledge_base_definitions",
        sa.Column(
            "id",
            sa.String(length=256),
            nullable=False,
            comment=("Contributed name, dotted, under a prefix its contributor owns."),
        ),
        sa.Column("prefix", sa.String(length=256), nullable=False),
        sa.Column("version", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "configuration_fields_json",
            sa.Text(),
            nullable=False,
            comment=(
                "JSON-serialized FieldSpec list the pod declared. Fred renders "
                "the instance configuration form from it and never interprets a value."
            ),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["prefix"], ["knowledge_base_prefixes.prefix"]),
    )
    op.create_index(
        "ix_knowledge_base_definitions_prefix",
        "knowledge_base_definitions",
        ["prefix"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_base_definitions_prefix",
        table_name="knowledge_base_definitions",
    )
    op.drop_table("knowledge_base_definitions")
    op.drop_table("knowledge_base_prefixes")
