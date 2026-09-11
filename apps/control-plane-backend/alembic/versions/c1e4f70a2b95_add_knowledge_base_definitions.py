"""add knowledge_base_definitions

Revision ID: c1e4f70a2b95
Revises: b7d4c1a9e802
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
down_revision: Union[str, None] = "b7d4c1a9e802"  # pragma: allowlist secret
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_definitions",
        sa.Column("provider_id", sa.String(length=256), nullable=False),
        sa.Column("definition_id", sa.String(length=256), nullable=False),
        sa.Column(
            "client_id",
            sa.String(length=255),
            nullable=False,
            comment=(
                "Confidential M2M client bound to this provider at its first "
                "publication. Every publication for this provider is checked "
                "against it."
            ),
        ),
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
        sa.PrimaryKeyConstraint("provider_id", "definition_id"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_base_definitions")
